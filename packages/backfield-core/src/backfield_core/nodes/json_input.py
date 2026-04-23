"""JSONInput node — structured params with required ``text`` (ported from agate-ai-platform).

All top-level keys from the node's stored ``params`` are passed through to downstream nodes
unchanged (except optional stripping of React-only keys). PlaceExtract and similar nodes
flatten upstream outputs and substitute ``{headline}``, ``{results.images}``, etc. from
that merged dict.
"""

from __future__ import annotations

from typing import Any

# Keys that may appear on React Flow ``data`` but must not be persisted or executed.
_STRIP_PARAM_KEYS = frozenset({"onChange"})


def json_input_output_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Build the same executor output as :func:`run_json_input` from a document dict.

    Used for S3 batch JSON objects so headline, url, publication, and other top-level
    keys are passed through like node ``params``, not only ``text``.
    """
    if not isinstance(data, dict):
        raise ValueError("JSONInput requires params to be a JSON object (dict).")

    cleaned = {k: v for k, v in data.items() if k not in _STRIP_PARAM_KEYS}
    text = cleaned.get("text")
    if text is None or not str(text).strip():
        raise ValueError(
            "JSONInput requires a non-empty top-level string field 'text'. "
            "Add or edit the JSON in the node panel before running the flow."
        )
    out = dict(cleaned)
    out["text"] = str(text)
    return out


def run_json_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    del inputs
    return json_input_output_from_dict(params)
