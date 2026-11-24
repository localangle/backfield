"""POST .../cleanup/{entity}/aliases: add, restore or suppress aliases, one item at a time."""

from __future__ import annotations

from backfield_entities.cleanup.alias_items import (
    AliasRequestBody,
    AliasResponse,
    apply_alias_items,
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


def post_cleanup_aliases(
    entity: EntityName,
    body: AliasRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> AliasResponse:
    """Add a name a record is also known by, or take one away.

    `add` brings back a suppressed name too. `suppress` hides a name without deleting it, so its
    history stays. `dry_run` (the default) changes nothing. Each item succeeds or fails on its own.
    """
    try:
        return apply_alias_items(
            session,
            cleanup_entity_models(entity),
            stylebook_id=context.stylebook_id,
            body=body,
            caller=action_caller(context.auth),
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
