"""POST .../cleanup/{entity}/merges: merge canonicals, one item at a time."""

from __future__ import annotations

from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.merge_items import (
    MergeRequestBody,
    MergeResponse,
    apply_merge_items,
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


def post_cleanup_merges(
    entity: EntityName,
    body: MergeRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> MergeResponse:
    """Merge each source into its survivor.

    Carries the source's aliases, metadata, connections, and linked records to the survivor,
    records where the old id went, and queues a search re-index. `dry_run` (the default) reports
    what would happen and changes nothing. Each item succeeds or fails on its own.
    """
    try:
        return apply_merge_items(
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
