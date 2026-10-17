"""Processing Guard — deterministic admission checks before expensive work."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agate_nodes.processing_guard.criteria import (
    ProcessingGuardParams,
    evaluate_criteria,
)

PROCESSING_GUARD_SUMMARY_KEY = "processing_guard"
NEEDS_ATTENTION_DISPOSITION = "needs_attention"


def run_processing_guard(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Pass the story through, attaching findings when a criterion holds it."""
    from agate_runtime.upstream_input import flatten_upstream_inputs

    flattened = flatten_upstream_inputs(inputs if isinstance(inputs, dict) else {})
    text = flattened.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "Processing Guard requires non-empty upstream text from Text Input, "
            "JSON Input, or S3 Input."
        )
    try:
        parsed = ProcessingGuardParams.model_validate(params if isinstance(params, dict) else {})
    except ValidationError as exc:
        raise ValueError(f"Processing Guard settings are invalid: {exc}") from exc

    summary = evaluate_criteria(parsed.criteria, text=text)
    output = dict(flattened)
    output["text"] = text
    output[PROCESSING_GUARD_SUMMARY_KEY] = summary.model_dump()
    return output


def guard_summary_needs_attention(output: dict[str, Any]) -> bool:
    """True when this node's summary says later steps should not run."""
    summary = output.get(PROCESSING_GUARD_SUMMARY_KEY)
    if not isinstance(summary, dict):
        return False
    return summary.get("disposition") == NEEDS_ATTENTION_DISPOSITION


def mark_guard_continued_anyway(output: dict[str, Any]) -> None:
    """Record that this attempt kept going after a limit was exceeded."""
    summary = output.get(PROCESSING_GUARD_SUMMARY_KEY)
    if isinstance(summary, dict):
        summary["continued_anyway"] = True
