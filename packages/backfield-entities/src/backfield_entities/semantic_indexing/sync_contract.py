"""Result contracts for semantic document synchronization (Issue 4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType


@dataclass(frozen=True)
class SemanticSyncScope:
    """Article-scoped semantic sync input."""

    project_id: int
    article_id: int
    entity_type: SemanticBuilderEntityType | None = None


@dataclass
class SemanticSyncSummary:
    """Counts from one entity-type synchronization pass."""

    entity_type: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    pending: int = 0
    failed_unchanged: int = 0
    unsupported: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "entity_type": self.entity_type,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deactivated": self.deactivated,
            "pending": self.pending,
            "failed_unchanged": self.failed_unchanged,
            "unsupported": self.unsupported,
        }


@dataclass(frozen=True)
class SemanticSyncResult:
    """Combined sync outcome for one or more entity types."""

    summaries: tuple[SemanticSyncSummary, ...] = field(default_factory=tuple)

    def merged(self) -> SemanticSyncSummary:
        if not self.summaries:
            raise ValueError("SemanticSyncResult has no summaries")
        if len(self.summaries) == 1:
            return self.summaries[0]
        merged = SemanticSyncSummary(entity_type=self.summaries[0].entity_type)
        for summary in self.summaries:
            merged.created += summary.created
            merged.updated += summary.updated
            merged.unchanged += summary.unchanged
            merged.deactivated += summary.deactivated
            merged.pending += summary.pending
            merged.failed_unchanged += summary.failed_unchanged
            merged.unsupported += summary.unsupported
        return merged
