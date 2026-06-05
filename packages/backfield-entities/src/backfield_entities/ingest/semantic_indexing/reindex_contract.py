"""Contracts for focused semantic re-index jobs (Issue 8)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_entities.ingest.semantic_indexing.contracts import SemanticBuilderEntityType

SEMANTIC_REINDEX_TASK_NAME = "worker.tasks.reindex_semantic_documents"


@dataclass(frozen=True)
class SemanticReindexScope:
    """Article-scoped semantic sync + embedding work."""

    project_id: int
    article_id: int
    entity_type: SemanticBuilderEntityType | None = None
