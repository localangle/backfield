"""Article-scoped semantic document synchronization entry points."""

from __future__ import annotations

from sqlmodel import Session

from backfield_stylebook.entity_types import EntityType
from backfield_stylebook.semantic_indexing.builders import (
    SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES,
    semantic_builder_supported,
)
from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_stylebook.semantic_indexing.location import sync_location_semantic_documents
from backfield_stylebook.semantic_indexing.person import sync_person_semantic_documents
from backfield_stylebook.semantic_indexing.sync_contract import (
    SemanticSyncResult,
    SemanticSyncScope,
    SemanticSyncSummary,
)


def _sync_entity_type(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    entity_type: SemanticBuilderEntityType,
) -> SemanticSyncSummary:
    if entity_type == "person":
        return sync_person_semantic_documents(
            session,
            project_id=project_id,
            article_id=article_id,
        )
    return sync_location_semantic_documents(
        session,
        project_id=project_id,
        article_id=article_id,
    )


def sync_semantic_documents_for_article(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    entity_types: tuple[SemanticBuilderEntityType, ...] | None = None,
) -> SemanticSyncResult:
    """Compare builder output to stored rows for one article scope."""
    selected = entity_types or SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES
    summaries: list[SemanticSyncSummary] = []
    for entity_type in selected:
        if not semantic_builder_supported(entity_type):
            summaries.append(
                SemanticSyncSummary(
                    entity_type=str(entity_type),
                    unsupported=1,
                )
            )
            continue
        summaries.append(
            _sync_entity_type(
                session,
                project_id=project_id,
                article_id=article_id,
                entity_type=entity_type,
            )
        )
    return SemanticSyncResult(summaries=tuple(summaries))


def sync_semantic_documents_for_scope(
    session: Session,
    scope: SemanticSyncScope,
) -> SemanticSyncResult:
    entity_types: tuple[SemanticBuilderEntityType, ...] | None = None
    if scope.entity_type is not None:
        entity_types = (scope.entity_type,)
    return sync_semantic_documents_for_article(
        session,
        project_id=scope.project_id,
        article_id=scope.article_id,
        entity_types=entity_types,
    )


def sync_semantic_documents_for_entity_type(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    entity_type: EntityType,
) -> SemanticSyncResult:
    if entity_type not in SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES:
        return SemanticSyncResult(
            summaries=(
                SemanticSyncSummary(
                    entity_type=str(entity_type),
                    unsupported=1,
                ),
            )
        )
    return sync_semantic_documents_for_article(
        session,
        project_id=project_id,
        article_id=article_id,
        entity_types=(entity_type,),  # type: ignore[arg-type]
    )
