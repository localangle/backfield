"""Ground extraction candidates in chunk ownership ranges."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from agate_utils.text_chunking import DocumentChunk

T = TypeVar("T")


@dataclass(frozen=True)
class GroundedSpan:
    start: int
    end: int
    text: str


@dataclass
class ChunkCandidate(Generic[T]):
    """Internal candidate produced from one chunk before document-level merge."""

    payload: T
    chunk_index: int
    evidence: GroundedSpan | None
    owned: bool = False
    mention_spans: list[GroundedSpan] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


def locate_evidence_span(
    *,
    source_text: str,
    chunk: DocumentChunk,
    evidence_text: str,
    prefer_owned: bool = True,
) -> GroundedSpan | None:
    """Locate ``evidence_text`` inside the chunk context; prefer ownership when possible."""
    needle = (evidence_text or "").strip()
    if not needle:
        return None

    context = source_text[chunk.context_start : chunk.context_end]
    search_from = 0
    owned_hit: GroundedSpan | None = None
    any_hit: GroundedSpan | None = None

    while True:
        local = context.find(needle, search_from)
        if local < 0:
            break
        global_start = chunk.context_start + local
        global_end = global_start + len(needle)
        span = GroundedSpan(
            start=global_start,
            end=global_end,
            text=source_text[global_start:global_end],
        )
        if any_hit is None:
            any_hit = span
        if chunk.ownership_start <= global_start < chunk.ownership_end:
            owned_hit = span
            break
        search_from = local + 1

    if prefer_owned and owned_hit is not None:
        return owned_hit
    return owned_hit or any_hit


def filter_owned_candidates(candidates: list[ChunkCandidate[T]]) -> list[ChunkCandidate[T]]:
    """Keep candidates whose evidence starts inside their chunk ownership range."""
    owned: list[ChunkCandidate[T]] = []
    for candidate in candidates:
        if candidate.evidence is None:
            continue
        if candidate.owned:
            owned.append(candidate)
    return owned


def mark_ownership(
    candidate: ChunkCandidate[T],
    *,
    chunk: DocumentChunk,
) -> ChunkCandidate[T]:
    """Set ``owned`` when primary evidence begins inside the ownership range."""
    if candidate.evidence is None:
        candidate.owned = False
        return candidate
    start = candidate.evidence.start
    candidate.owned = chunk.ownership_start <= start < chunk.ownership_end
    return candidate


def union_mention_texts(*groups: list[str]) -> list[str]:
    """Preserve first-seen mention order while dropping exact duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for text in group:
            cleaned = text.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            out.append(cleaned)
    return out
