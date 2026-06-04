"""Run focused semantic re-index jobs after manual edits (Issue 8)."""

from __future__ import annotations

from typing import Any

from backfield_stylebook.semantic_indexing.builders import SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES
from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_stylebook.semantic_indexing.reindex_contract import SemanticReindexScope
from backfield_stylebook.semantic_indexing.sync import sync_semantic_documents_for_article
from sqlmodel import Session

from worker.semantic_indexing.embed import embed_pending_semantic_documents


def run_semantic_reindex_for_scope(
    session: Session,
    scope: SemanticReindexScope,
) -> dict[str, Any]:
    """Sync and embed pending semantic documents for one article scope."""
    entity_types: tuple[SemanticBuilderEntityType, ...]
    if scope.entity_type is None:
        entity_types = SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES
    else:
        entity_types = (scope.entity_type,)

    sync_result = sync_semantic_documents_for_article(
        session,
        project_id=scope.project_id,
        article_id=scope.article_id,
        entity_types=entity_types,
    )
    session.commit()

    embedding_summary = embed_pending_semantic_documents(
        session,
        project_id=scope.project_id,
        article_id=scope.article_id,
        entity_types=entity_types,
    )
    session.commit()

    return {
        "project_id": scope.project_id,
        "article_id": scope.article_id,
        "entity_type": scope.entity_type,
        "sync": [summary.as_dict() for summary in sync_result.summaries],
        "embedding": embedding_summary.as_dict(),
    }
