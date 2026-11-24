"""Dismissal and integrity reads."""

from __future__ import annotations

from backfield_entities.cleanup.cursor import InvalidCursorError
from backfield_entities.cleanup.dismissal_items import (
    DismissalRequestBody,
    DismissalResponse,
    apply_dismissal_items,
)
from backfield_entities.cleanup.dismissals_read import (
    DISMISSALS_DEFAULT_LIMIT,
    DISMISSALS_MAX_LIMIT,
    DismissalPage,
    list_dismissals,
)
from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.integrity import IntegrityReport, build_integrity_report
from backfield_entities.cleanup.runs import RunNotFoundError
from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    action_caller,
    get_cleanup_context,
    require_cleanup_apply,
    require_cleanup_read,
)


def get_cleanup_dismissals(
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    check_id: str | None = Query(default=None, description="Only dismissals for this check."),
    cursor: str | None = Query(default=None, description="`next_cursor` from the previous page."),
    limit: int = Query(default=DISMISSALS_DEFAULT_LIMIT, ge=1, le=DISMISSALS_MAX_LIMIT),
) -> DismissalPage:
    """Issues editors set aside, so a client does not raise them again."""
    try:
        return list_dismissals(
            session,
            stylebook_id=context.stylebook_id,
            check_id=check_id,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def get_cleanup_integrity(
    entity: EntityName,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> IntegrityReport:
    """Read-only report on the catalog's own invariants for one kind of entity."""
    return build_integrity_report(
        session, cleanup_entity_models(entity), stylebook_id=context.stylebook_id
    )


def post_cleanup_dismissals(
    body: DismissalRequestBody,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> DismissalResponse:
    """Set check results aside, or bring them back, with a reason you choose.

    Duplicate checks are dismissed one pair at a time (`left_id`, `right_id`); checks that list
    single canonicals use `canonical_id`. `dry_run` (the default) changes nothing. Each item
    succeeds or fails on its own.
    """
    try:
        return apply_dismissal_items(
            session,
            stylebook_id=context.stylebook_id,
            body=body,
            caller=action_caller(context.auth),
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
