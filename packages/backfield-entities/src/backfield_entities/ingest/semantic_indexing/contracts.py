"""Shared contracts for deterministic semantic document builders (Issue 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backfield_db.semantic_indexing import SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE

from backfield_entities.registry.entity_types import EntityType

SemanticBuilderEntityType = Literal["person", "location", "organization"]

SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES: tuple[SemanticBuilderEntityType, ...] = (
    "person",
    "location",
    "organization",
)


@dataclass(frozen=True)
class SemanticDocumentSourceKey:
    """Stable identity for one occurrence-level semantic document."""

    entity_type: SemanticBuilderEntityType
    occurrence_id: int

    def as_string(self) -> str:
        return f"{self.entity_type}:occurrence:{self.occurrence_id}"


@dataclass(frozen=True)
class SemanticDocumentDraft:
    """Deterministic semantic document payload before persistence."""

    source_key: SemanticDocumentSourceKey
    document_kind: str
    search_text: str
    source_hash: str
    project_id: int
    article_id: int
    entity_id: int
    mention_id: int
    occurrence_id: int
    active: bool = True


@dataclass(frozen=True)
class SemanticDocumentBuildSkip:
    """Occurrence excluded from active semantic indexing."""

    entity_type: SemanticBuilderEntityType
    occurrence_id: int
    reason: str


@dataclass(frozen=True)
class SemanticDocumentUnsupportedType:
    """Entity type has no semantic document builder yet."""

    entity_type: EntityType | str


SemanticDocumentBuilderOutcome = (
    SemanticDocumentDraft | SemanticDocumentBuildSkip | SemanticDocumentUnsupportedType
)


DEFAULT_DOCUMENT_KIND = SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE

SKIP_ARTICLE_DELETED = "article_deleted"
SKIP_MENTION_DELETED = "mention_deleted"
SKIP_OCCURRENCE_SUPPRESSED = "occurrence_suppressed"
