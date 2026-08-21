"""JSONInput node — structured params with required ``text``.

All top-level keys from the node's stored ``params`` are passed through to downstream nodes
unchanged (except optional stripping of React-only keys). PlaceExtract and similar nodes
flatten upstream outputs and substitute ``{headline}``, ``{results.images}``, etc. from
that merged dict.

Some CMS exports reuse ``text`` for a short section label (e.g. "Music") while the
article body lives in ``article_text``, ``body``, or ``content``. :func:`resolve_document_body_text`
picks the longest non-empty string among known body fields so extraction sees real copy.

Multi-file uploads store two or more objects under the reserved ``documents`` key. Each
entry is one pipeline item (same as S3 Input). A single pasted/uploaded object keeps the
flat params shape for backward compatibility.
"""

from __future__ import annotations

from typing import Any

DOCUMENTS_PARAM = "documents"
SOURCE_FILE_KEY = "source_file"
PUBLIC_ALIAS_PARAM = "public_alias"
JSON_INPUT_MAX_DOCUMENTS = 20
DEFAULT_INLINE_SOURCE_FILE = "inline:json"

_STRIP_PARAM_KEYS = frozenset({"onChange", DOCUMENTS_PARAM})

# Dropped when unpacking a documents[] entry (node-level / editor keys).
_DOCUMENT_ENTRY_STRIP_KEYS = frozenset(
    {
        "onChange",
        DOCUMENTS_PARAM,
        PUBLIC_ALIAS_PARAM,
        "__jsonInputInvalid",
    }
)

# Dropped from flat single-document params before execution (keep public_alias passthrough).
_FLAT_PARAM_STRIP_KEYS = frozenset(
    {
        "onChange",
        DOCUMENTS_PARAM,
        "__jsonInputInvalid",
    }
)

_BODY_TEXT_KEYS: tuple[str, ...] = (
    "article_text",
    "articleBody",
    "article_body",
    "richTextBody",
    "rich_text",
    "body",
    "content",
    "story",
    "full_text",
    "html",
    "text",
)


def resolve_document_body_text(data: dict[str, Any]) -> str | None:
    """Return the best article body string for downstream LLM nodes."""
    best: str | None = None
    best_len = -1
    for key in _BODY_TEXT_KEYS:
        raw = data.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        if len(value) > best_len:
            best_len = len(value)
            best = value
    return best


def json_input_output_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Build the same executor output as :func:`run_json_input` from a document dict."""
    if not isinstance(data, dict):
        raise ValueError("JSONInput requires params to be a JSON object (dict).")

    cleaned = {key: value for key, value in data.items() if key not in _STRIP_PARAM_KEYS}
    resolved = resolve_document_body_text(cleaned)
    if not resolved:
        raise ValueError(
            "JSONInput requires a non-empty article body. Provide one of: "
            + ", ".join(_BODY_TEXT_KEYS)
            + ". When several are set, the longest non-empty field is used."
        )
    out = dict(cleaned)
    out["text"] = resolved
    return out


def run_json_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    del inputs
    return json_input_output_from_dict(params)


def _document_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Return article fields from a documents[] entry (drops node-level keys)."""
    return {
        key: value
        for key, value in raw.items()
        if key not in _DOCUMENT_ENTRY_STRIP_KEYS
    }


def flat_document_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """Article fields from a single-document (flat) JSONInput params object."""
    return {
        key: value
        for key, value in params.items()
        if key not in _FLAT_PARAM_STRIP_KEYS
    }


def raw_documents_list(params: dict[str, Any]) -> list[Any] | None:
    """Return the ``documents`` list when present, else ``None``."""
    raw = params.get(DOCUMENTS_PARAM)
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("JSONInput 'documents' must be a list of JSON objects.")
    return raw


def is_json_input_multi_document(params: dict[str, Any]) -> bool:
    """True when params hold two or more uploaded documents (batch path)."""
    docs = raw_documents_list(params)
    return docs is not None and len(docs) >= 2


def normalize_source_file(raw: Any, *, fallback: str = DEFAULT_INLINE_SOURCE_FILE) -> str:
    if raw is None:
        return fallback
    cleaned = str(raw).strip()
    return cleaned or fallback


def parse_documents_entries(
    params: dict[str, Any],
    *,
    max_documents: int = JSON_INPUT_MAX_DOCUMENTS,
) -> list[tuple[str, dict[str, Any]]]:
    """Validate ``documents`` and return ``(source_file, article_payload)`` pairs.

    Does not require a non-empty body (save-time may allow empty ``text``); callers that
    execute a run should normalize via :func:`json_input_output_from_dict`.
    """
    docs = raw_documents_list(params)
    if docs is None:
        raise ValueError("JSONInput params have no 'documents' list.")
    if len(docs) < 2:
        raise ValueError(
            "JSONInput 'documents' requires at least two files for batch mode; "
            "use flat params for a single document."
        )
    if len(docs) > max_documents:
        raise ValueError(
            f"JSONInput accepts at most {max_documents} files at a time "
            f"(got {len(docs)})."
        )

    out: list[tuple[str, dict[str, Any]]] = []
    for index, entry in enumerate(docs):
        if not isinstance(entry, dict):
            raise ValueError(
                f"JSONInput documents[{index}] must be a JSON object."
            )
        source_file = normalize_source_file(
            entry.get(SOURCE_FILE_KEY),
            fallback=f"document-{index + 1}.json",
        )
        payload = {**_document_payload(entry), SOURCE_FILE_KEY: source_file}
        out.append((source_file, payload))
    return out


def documents_for_batch_execution(
    params: dict[str, Any],
    *,
    max_documents: int = JSON_INPUT_MAX_DOCUMENTS,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(source_file, normalized_doc)`` ready for ``agate_processed_item`` rows."""
    entries = parse_documents_entries(params, max_documents=max_documents)
    normalized: list[tuple[str, dict[str, Any]]] = []
    for source_file, payload in entries:
        doc = json_input_output_from_dict(payload)
        normalized.append((source_file, doc))
    return normalized


def single_document_from_params(params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Resolve one document for the single-item path.

    Prefers a length-1 ``documents`` list when present; otherwise uses flat params.
    """
    docs = raw_documents_list(params)
    if docs is not None:
        if len(docs) == 0:
            raise ValueError("JSONInput 'documents' list is empty.")
        if len(docs) >= 2:
            raise ValueError(
                "JSONInput with multiple documents uses batch setup, not single-item ingress."
            )
        entry = docs[0]
        if not isinstance(entry, dict):
            raise ValueError("JSONInput documents[0] must be a JSON object.")
        source_file = normalize_source_file(entry.get(SOURCE_FILE_KEY))
        payload = _document_payload(entry)
        if SOURCE_FILE_KEY not in payload and source_file != DEFAULT_INLINE_SOURCE_FILE:
            payload = {**payload, SOURCE_FILE_KEY: source_file}
        return payload, source_file

    return flat_document_from_params(params), DEFAULT_INLINE_SOURCE_FILE
