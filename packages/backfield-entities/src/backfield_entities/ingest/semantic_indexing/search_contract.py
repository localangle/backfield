"""Shared contracts for semantic mention search (Issue 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QuoteStatusFilter = Literal["any", "quote_only", "mention_only"]


@dataclass
class SemanticMentionSearchFilters:
    """Shared structured filters across entity-type search endpoints."""

    article_id: int | None = None
    canonical_id: str | None = None
    entity_id: int | None = None
    mention_id: int | None = None
    occurrence_id: int | None = None
    active_only: bool = True
    quote_status: QuoteStatusFilter = "any"


@dataclass
class PersonSemanticSearchFilters(SemanticMentionSearchFilters):
    person_type: str | None = None
    public_figure: bool | None = None
    nature: str | None = None
    title: str | None = None
    affiliation: str | None = None


@dataclass
class LocationSemanticSearchFilters(SemanticMentionSearchFilters):
    location_type: str | None = None


@dataclass(frozen=True)
class SemanticMentionSearchHit:
    """One evidence-centric semantic search result row."""

    semantic_document_id: int
    entity_type: str
    score: float
    article: dict[str, Any]
    entity: dict[str, Any]
    canonical: dict[str, Any] | None
    mention: dict[str, Any]
    occurrence: dict[str, Any]
    search_text: str


@dataclass
class SemanticMentionSearchResult:
    total: int
    limit: int
    offset: int
    hits: tuple[SemanticMentionSearchHit, ...] = field(default_factory=tuple)
