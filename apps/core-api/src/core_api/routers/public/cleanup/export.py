"""GET .../cleanup/{entity}/export: keyset-paged export of a Stylebook's canonicals."""

from __future__ import annotations

from datetime import date, datetime

from backfield_entities.cleanup.cursor import InvalidCursorError
from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.export import (
    EXPORT_DEFAULT_LIMIT,
    EXPORT_MAX_LIMIT,
    CleanupExportPage,
    ExportFilters,
    export_canonicals,
)
from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
)


def get_cleanup_export(
    entity: EntityName,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    cursor: str | None = Query(default=None, description="`next_cursor` from the previous page."),
    limit: int = Query(default=EXPORT_DEFAULT_LIMIT, ge=1, le=EXPORT_MAX_LIMIT),
    updated_since: datetime | None = Query(
        default=None, description="Only canonicals changed at or after this time."
    ),
    mentioned_from: date | None = Query(
        default=None, description="Only canonicals with an active mention published on or after."
    ),
    mentioned_to: date | None = Query(
        default=None, description="Only canonicals with an active mention published on or before."
    ),
    kind: str | None = Query(default=None, description="Place kind, person type or org type."),
) -> CleanupExportPage:
    """Page through every active canonical of one kind, with mention and alias counts."""
    try:
        return export_canonicals(
            session,
            cleanup_entity_models(entity),
            stylebook_id=context.stylebook_id,
            filters=ExportFilters(
                updated_since=updated_since,
                mentioned_from=mentioned_from,
                mentioned_to=mentioned_to,
                kind=kind,
            ),
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
