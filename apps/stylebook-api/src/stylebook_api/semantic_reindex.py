"""Enqueue focused semantic re-index jobs after Stylebook manual edits."""

from __future__ import annotations

import os

from backfield_entities.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_entities.semantic_indexing.reindex import semantic_reindex_scopes_for_entity
from backfield_entities.semantic_indexing.reindex_contract import SEMANTIC_REINDEX_TASK_NAME
from celery import Celery
from sqlmodel import Session

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def _celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def enqueue_semantic_reindex(
    *,
    project_id: int,
    article_id: int,
    entity_type: SemanticBuilderEntityType | None = None,
) -> None:
    """Queue one article-scoped semantic sync + embedding job."""
    celery_app.send_task(
        SEMANTIC_REINDEX_TASK_NAME,
        args=[int(project_id), int(article_id), entity_type],
        queue=_celery_queue(),
    )


def enqueue_semantic_reindex_for_entity(
    session: Session,
    *,
    project_id: int,
    entity_type: SemanticBuilderEntityType,
    entity_id: int,
    article_id: int | None = None,
) -> None:
    """Queue semantic re-index jobs for one entity across affected articles."""
    scopes = semantic_reindex_scopes_for_entity(
        session,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        article_id=article_id,
    )
    for scope in scopes:
        enqueue_semantic_reindex(
            project_id=scope.project_id,
            article_id=scope.article_id,
            entity_type=scope.entity_type,
        )
