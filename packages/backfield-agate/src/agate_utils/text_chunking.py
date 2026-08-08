"""Deterministic document chunking with ownership ranges.

Chunks are execution units for LLM extractors. The original document text remains
canonical; each chunk carries overlapping context plus a non-overlapping ownership
range used to filter grounded extraction results.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

CHUNKING_STRATEGY_VERSION = "paragraph_sentence_v1"
TRANSIENT_CHUNK_ENVELOPE_KEY = "__document_chunk_envelope"
CHUNKING_SUMMARY_KEY = "chunking_summary"

DEFAULT_TARGET_TOKENS = 4000
DEFAULT_OVERLAP_TOKENS = 250
MAX_CHUNKS = 50
ARTICLE_METADATA_PROMPT_TOKENS = 4000

# Approximate tokens ≈ ceil(chars / 4). Model-neutral and stable across providers.
_CHARS_PER_TOKEN = 4

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_WHITESPACE_RUN = re.compile(r"\s+")


def approximate_token_count(text: str) -> int:
    """Return a stable approximate token count for budgeting and chunk sizing."""
    if not text:
        return 0
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def chars_for_tokens(tokens: int) -> int:
    return max(0, int(tokens) * _CHARS_PER_TOKEN)


class DocumentChunk(BaseModel):
    """One chunk with context and exclusive ownership offsets into the source text."""

    index: int = Field(ge=0)
    text: str
    context_start: int = Field(ge=0)
    context_end: int = Field(ge=0)
    ownership_start: int = Field(ge=0)
    ownership_end: int = Field(ge=0)
    approximate_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_ranges(self) -> DocumentChunk:
        if self.context_end < self.context_start:
            raise ValueError("context_end must be >= context_start")
        if self.ownership_end < self.ownership_start:
            raise ValueError("ownership_end must be >= ownership_start")
        if not (
            self.context_start
            <= self.ownership_start
            <= self.ownership_end
            <= self.context_end
        ):
            raise ValueError("ownership range must lie within context range")
        return self


class DocumentChunkEnvelope(BaseModel):
    """Typed envelope carried transiently between Chunker and extract nodes."""

    version: Literal["1"] = "1"
    strategy: str = CHUNKING_STRATEGY_VERSION
    text: str
    target_tokens: int = Field(default=DEFAULT_TARGET_TOKENS, ge=1)
    overlap_tokens: int = Field(default=DEFAULT_OVERLAP_TOKENS, ge=0)
    split_required: bool = False
    chunks: list[DocumentChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_chunks(self) -> DocumentChunkEnvelope:
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        if len(self.chunks) > MAX_CHUNKS:
            raise ValueError(
                f"Document requires {len(self.chunks)} chunks; maximum allowed is {MAX_CHUNKS}."
            )
        for chunk in self.chunks:
            if chunk.text != self.text[chunk.context_start : chunk.context_end]:
                raise ValueError(
                    f"Chunk {chunk.index} text does not match source slice "
                    f"[{chunk.context_start}:{chunk.context_end}]"
                )
        if self.chunks:
            ownerships = sorted(
                (c.ownership_start, c.ownership_end, c.index) for c in self.chunks
            )
            cursor = 0
            for start, end, index in ownerships:
                if start != cursor:
                    raise ValueError(
                        f"Ownership gap or overlap before chunk {index} "
                        f"(expected start {cursor}, got {start})"
                    )
                cursor = end
            if cursor != len(self.text):
                raise ValueError(
                    f"Ownership ranges must cover the full document "
                    f"(covered {cursor}, length {len(self.text)})"
                )
        return self


class ChunkingSummary(BaseModel):
    """Bounded public summary safe for run JSON / panel output."""

    strategy: str
    target_tokens: int
    overlap_tokens: int
    split_required: bool
    chunk_count: int
    approximate_document_tokens: int
    chunks: list[dict[str, Any]]


def truncate_text_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate ``text`` to roughly ``max_tokens``, preferring paragraph then sentence."""
    if max_tokens <= 0:
        return "", bool(text)
    if approximate_token_count(text) <= max_tokens:
        return text, False

    max_chars = chars_for_tokens(max_tokens)
    if len(text) <= max_chars:
        return text, False

    window = text[:max_chars]
    cut = _best_boundary(window)
    truncated = window[:cut].rstrip()
    if not truncated:
        truncated = window.rstrip()
    return truncated, True


def _best_boundary(window: str) -> int:
    """Prefer last paragraph break, then sentence break, else hard cut."""
    para = window.rfind("\n\n")
    if para >= max(1, len(window) // 4):
        return para
    sentence_end = 0
    for match in _SENTENCE_BOUNDARY.finditer(window):
        sentence_end = match.start() + 1
    if sentence_end >= max(1, len(window) // 4):
        return sentence_end
    return len(window)


def split_document_text(
    text: str,
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> DocumentChunkEnvelope:
    """Split ``text`` into overlapping chunks with exclusive ownership ranges."""
    source = text if isinstance(text, str) else ""
    if not source.strip():
        raise ValueError("Document Chunker requires non-empty text.")

    if target_tokens < 1:
        raise ValueError("target_tokens must be at least 1.")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative.")
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be smaller than target_tokens.")

    target_chars = chars_for_tokens(target_tokens)
    overlap_chars = chars_for_tokens(overlap_tokens)

    if len(source) <= target_chars:
        chunk = DocumentChunk(
            index=0,
            text=source,
            context_start=0,
            context_end=len(source),
            ownership_start=0,
            ownership_end=len(source),
            approximate_tokens=approximate_token_count(source),
        )
        return DocumentChunkEnvelope(
            text=source,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            split_required=False,
            chunks=[chunk],
        )

    ownership_starts = _plan_ownership_starts(source, target_chars)
    if len(ownership_starts) > MAX_CHUNKS:
        raise ValueError(
            f"This document would create {len(ownership_starts)} chunks "
            f"(maximum {MAX_CHUNKS}). Shorten the document or raise the chunk size."
        )

    chunks: list[DocumentChunk] = []
    for index, own_start in enumerate(ownership_starts):
        own_end = (
            ownership_starts[index + 1] if index + 1 < len(ownership_starts) else len(source)
        )
        context_start = max(0, own_start - overlap_chars) if index > 0 else 0
        context_end = (
            min(len(source), own_end + overlap_chars)
            if index + 1 < len(ownership_starts)
            else len(source)
        )
        # Align context to nearby whitespace when possible without leaving ownership.
        context_start = _snap_context_start(source, context_start, own_start)
        context_end = _snap_context_end(source, context_end, own_end)
        chunk_text = source[context_start:context_end]
        chunks.append(
            DocumentChunk(
                index=index,
                text=chunk_text,
                context_start=context_start,
                context_end=context_end,
                ownership_start=own_start,
                ownership_end=own_end,
                approximate_tokens=approximate_token_count(chunk_text),
            )
        )

    return DocumentChunkEnvelope(
        text=source,
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
        split_required=True,
        chunks=chunks,
    )


def _plan_ownership_starts(source: str, target_chars: int) -> list[int]:
    starts = [0]
    cursor = 0
    length = len(source)
    while cursor < length:
        tentative_end = min(length, cursor + target_chars)
        if tentative_end >= length:
            break
        window = source[cursor:tentative_end]
        relative_cut = _best_boundary(window)
        own_end = cursor + relative_cut
        if own_end <= cursor:
            own_end = tentative_end
        # Skip leading whitespace for the next ownership start when possible.
        next_start = own_end
        while next_start < length and source[next_start].isspace():
            next_start += 1
        if next_start >= length:
            break
        if next_start <= cursor:
            next_start = min(length, cursor + target_chars)
        starts.append(next_start)
        cursor = next_start
        if len(starts) > MAX_CHUNKS + 1:
            break
    return starts


def _snap_context_start(source: str, context_start: int, ownership_start: int) -> int:
    if context_start <= 0 or context_start >= ownership_start:
        return context_start
    # Prefer starting after a whitespace run inside the overlap prefix.
    prefix = source[context_start:ownership_start]
    match = list(_WHITESPACE_RUN.finditer(prefix))
    if not match:
        return context_start
    last = match[-1]
    snapped = context_start + last.end()
    # Keep some overlap context when possible; never snap away the entire overlap.
    return snapped if snapped < ownership_start else context_start


def _snap_context_end(source: str, context_end: int, ownership_end: int) -> int:
    if context_end >= len(source) or context_end <= ownership_end:
        return context_end
    suffix = source[ownership_end:context_end]
    match = _WHITESPACE_RUN.search(suffix)
    if not match:
        return context_end
    snapped = ownership_end + match.start()
    return snapped if snapped >= ownership_end else context_end


def envelope_from_payload(payload: Any) -> DocumentChunkEnvelope | None:
    """Parse a transient envelope from flattened upstream state when present."""
    if isinstance(payload, DocumentChunkEnvelope):
        return payload
    if not isinstance(payload, dict):
        return None
    raw = payload.get(TRANSIENT_CHUNK_ENVELOPE_KEY)
    if raw is None:
        return None
    if isinstance(raw, DocumentChunkEnvelope):
        return raw
    if isinstance(raw, dict):
        return DocumentChunkEnvelope.model_validate(raw)
    raise ValueError("Invalid document chunk envelope upstream.")


def build_chunking_summary(envelope: DocumentChunkEnvelope) -> dict[str, Any]:
    """Build a bounded public summary (no full chunk texts)."""
    previews: list[dict[str, Any]] = []
    for chunk in envelope.chunks:
        owned = envelope.text[chunk.ownership_start : chunk.ownership_end]
        preview = owned[:160].replace("\n", " ").strip()
        if len(owned) > 160:
            preview = f"{preview}…"
        previews.append(
            {
                "index": chunk.index,
                "approximate_tokens": chunk.approximate_tokens,
                "ownership_start": chunk.ownership_start,
                "ownership_end": chunk.ownership_end,
                "preview": preview,
            }
        )
    summary = ChunkingSummary(
        strategy=envelope.strategy,
        target_tokens=envelope.target_tokens,
        overlap_tokens=envelope.overlap_tokens,
        split_required=envelope.split_required,
        chunk_count=len(envelope.chunks),
        approximate_document_tokens=approximate_token_count(envelope.text),
        chunks=previews,
    )
    return summary.model_dump()


def single_chunk_envelope(text: str) -> DocumentChunkEnvelope:
    """Wrap plain text as a one-chunk envelope for unchunked extract paths."""
    source = text if isinstance(text, str) else ""
    if not source.strip():
        raise ValueError("Extraction requires non-empty text.")
    chunk = DocumentChunk(
        index=0,
        text=source,
        context_start=0,
        context_end=len(source),
        ownership_start=0,
        ownership_end=len(source),
        approximate_tokens=approximate_token_count(source),
    )
    return DocumentChunkEnvelope(
        text=source,
        target_tokens=max(DEFAULT_TARGET_TOKENS, approximate_token_count(source)),
        overlap_tokens=0,
        split_required=False,
        chunks=[chunk],
    )
