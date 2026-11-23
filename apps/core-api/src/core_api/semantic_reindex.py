"""Queue focused semantic re-index jobs after catalog changes made through Core API."""

from __future__ import annotations

from backfield_entities.ingest.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_entities.ingest.semantic_indexing.reindex import semantic_reindex_scopes_for_entity
from backfield_entities.ingest.semantic_indexing.reindex_contract import SEMANTIC_REINDEX_TASK_NAME
from sqlmodel import Session

from core_api.run_enqueue import enqueue_worker_task


def enqueue_semantic_reindex_for_entity(
    session: Session,
    *,
    project_id: int,
    entity_type: SemanticBuilderEntityType,
    entity_id: int,
) -> None:
    """Queue one re-index job per article the relinked record appears in.

    Same contract as the Stylebook API adapter: the library supplies the affected articles and
    the task name, and each app owns its own queue client.
    """
    scopes = semantic_reindex_scopes_for_entity(
        session,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        article_id=None,
    )
    for scope in scopes:
        enqueue_worker_task(
            SEMANTIC_REINDEX_TASK_NAME,
            [int(scope.project_id), int(scope.article_id), scope.entity_type],
        )
