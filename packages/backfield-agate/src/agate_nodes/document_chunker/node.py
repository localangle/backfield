"""DocumentChunker — split long documents into overlapping owned chunks."""

from __future__ import annotations

from typing import Any

from agate_utils.text_chunking import (
    CHUNKING_SUMMARY_KEY,
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_TARGET_TOKENS,
    TRANSIENT_CHUNK_ENVELOPE_KEY,
    build_chunking_summary,
    split_document_text,
)
from pydantic import BaseModel, Field, field_validator, model_validator


class DocumentChunkerParams(BaseModel):
    target_tokens: int = Field(default=DEFAULT_TARGET_TOKENS, ge=100, le=32000)
    overlap_tokens: int = Field(default=DEFAULT_OVERLAP_TOKENS, ge=0, le=8000)

    @field_validator("target_tokens", "overlap_tokens", mode="before")
    @classmethod
    def _coerce_int(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return value

    @model_validator(mode="after")
    def _overlap_lt_target(self) -> DocumentChunkerParams:
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("Overlap must be smaller than the target chunk size.")
        return self


def run_document_chunker(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    # Local import avoids agate_runtime package init → NODE_RUNNERS → this module.
    from agate_runtime.upstream_input import flatten_upstream_inputs

    flattened = flatten_upstream_inputs(inputs if isinstance(inputs, dict) else {})
    text = flattened.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "Document Chunker requires non-empty upstream text from Text Input, "
            "JSON Input, or S3 Input."
        )

    parsed = DocumentChunkerParams.model_validate(params if isinstance(params, dict) else {})
    envelope = split_document_text(
        text,
        target_tokens=parsed.target_tokens,
        overlap_tokens=parsed.overlap_tokens,
    )

    output = dict(flattened)
    output["text"] = envelope.text
    output[TRANSIENT_CHUNK_ENVELOPE_KEY] = envelope.model_dump()
    output[CHUNKING_SUMMARY_KEY] = build_chunking_summary(envelope)
    return output
