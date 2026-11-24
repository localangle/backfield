"""POST .../cleanup/candidates/{entity}/decisions: decide candidates, one item at a time."""

from __future__ import annotations

from backfield_entities.cleanup.decision_items import (
    DecisionRequestBody,
    DecisionResponse,
    apply_decision_items,
)
from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
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


def post_cleanup_decisions(
    entity: EntityName,
    body: DecisionRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> DecisionResponse:
    """Link candidates to existing records, create records from them, or defer them.

    `link` attaches the candidate to `canonical_id` (a retired record is refused). `create` makes a
    new record from the candidate; `name`, `kind` and, for locations, `geometry` override what the
    candidate carries. `defer` moves it out of the open queue without a record. Candidates in any
    project of this Stylebook can be decided. `dry_run` (the default) changes nothing. Each item
    succeeds or fails on its own, and repeating a decision that already stands is a no-op.
    """
    try:
        return apply_decision_items(
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
