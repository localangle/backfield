"""POST .../cleanup/{entity}/edits: change a record's own fields, one item at a time."""

from __future__ import annotations

from backfield_entities.cleanup.edit_items import EditRequestBody, EditResponse, apply_edit_items
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


def post_cleanup_edits(
    entity: EntityName,
    body: EditRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> EditResponse:
    """Change a record's name, kind or other details.

    Changing the name keeps the old name as an alias. Locations can also set or clear their
    geography and copy it onto the saved places that should follow it. `dry_run` (the default)
    changes nothing. Each item succeeds or fails on its own.
    """
    try:
        return apply_edit_items(
            session,
            cleanup_entity_models(entity),
            stylebook_id=context.stylebook_id,
            organization_id=int(context.project.organization_id),
            body=body,
            caller=action_caller(context.auth),
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
