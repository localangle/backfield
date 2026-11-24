"""POST .../cleanup/{entity}/retirements: retire or reinstate records, one item at a time."""

from __future__ import annotations

from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.removal_items import (
    RemovalResponse,
    RetirementRequestBody,
    apply_retirement_items,
)
from backfield_entities.cleanup.runs import RunNotFoundError
from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    action_caller,
    get_cleanup_context,
    require_cleanup_apply,
)
from core_api.semantic_reindex import enqueue_semantic_reindex_for_entity


def post_cleanup_retirements(
    entity: EntityName,
    body: RetirementRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> RemovalResponse:
    """Retire a record, or bring a retired one back.

    A retired record is inactive: it stops matching new mentions and drops out of public lists, and
    its open connections are closed. Records still linked to it are handled by
    `mention_disposition`: `refuse` (the default) stops if any are linked, `requeue` returns them to
    the review queue, `waive` marks them as not needing a record. `reinstate` makes it active again;
    it does not relink anything. `dry_run` (the default) changes nothing. Each item succeeds or
    fails on its own.
    """
    try:
        return apply_retirement_items(
            session,
            cleanup_entity_models(entity),
            stylebook_id=context.stylebook_id,
            organization_id=int(context.project.organization_id),
            body=body,
            caller=action_caller(context.auth),
            reindex=enqueue_semantic_reindex_for_entity,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
