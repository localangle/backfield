"""JSONInput node — structured params with required ``text`` (ported from agate-ai-platform).

All top-level keys from the node's stored ``params`` are passed through to downstream nodes
unchanged (except optional stripping of React-only keys). PlaceExtract and similar nodes
flatten upstream outputs and substitute ``{headline}``, ``{results.images}``, etc. from
that merged dict.

Some CMS exports reuse ``text`` for a short section label (e.g. "Music") while the
article body lives in ``article_text``, ``body``, or ``content``. :func:`resolve_document_body_text`
picks the longest non-empty string among known body fields so extraction sees real copy.
"""

from __future__ import annotations

from typing import Any

# Keys that may appear on React Flow ``data`` but must not be persisted or executed.
_STRIP_PARAM_KEYS = frozenset({"onChange"})

# When multiple fields exist, the longest non-empty string wins (first wins on ties).
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
    """Return the best article body string for downstream LLM nodes.

    Exporters sometimes put a category or section name in ``text`` and the narrative in
    ``article_text`` / ``body``. We prefer the longest non-empty candidate so PlaceExtract
    receives substantive copy.
    """
    best: str | None = None
    best_len = -1
    for key in _BODY_TEXT_KEYS:
        raw = data.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            continue
        ln = len(s)
        if ln > best_len:
            best_len = ln
            best = s
    return best


def json_input_output_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Build the same executor output as :func:`run_json_input` from a document dict.

    Used for S3 batch JSON objects so headline, url, publication, and other top-level
    keys are passed through like node ``params``, not only ``text``.
    """
    if not isinstance(data, dict):
        raise ValueError("JSONInput requires params to be a JSON object (dict).")

    cleaned = {k: v for k, v in data.items() if k not in _STRIP_PARAM_KEYS}
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
