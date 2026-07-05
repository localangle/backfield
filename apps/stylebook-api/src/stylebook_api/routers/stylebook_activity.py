"""Stylebook recent activity feed endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backfield_db import StylebookActivity
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-activity"])


class StylebookActivityEventOut(BaseModel):
    id: int
    stylebook_id: int
    project_id: int | None = None
    actor_type: str
    actor_user_id: int | None = None
    source: str
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    related_entity_label: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: StylebookActivity) -> StylebookActivityEventOut:
        return cls(
            id=int(row.id),  # type: ignore[arg-type]
            stylebook_id=int(row.stylebook_id),
            project_id=int(row.project_id) if row.project_id is not None else None,
            actor_type=str(row.actor_type),
            actor_user_id=int(row.actor_user_id) if row.actor_user_id is not None else None,
            source=str(row.source),
            event_type=str(row.event_type),
            entity_type=(str(row.entity_type) if row.entity_type else None),
            entity_id=(str(row.entity_id) if row.entity_id else None),
            entity_label=(str(row.entity_label) if row.entity_label else None),
            related_entity_type=(
                str(row.related_entity_type) if row.related_entity_type else None
            ),
            related_entity_id=(str(row.related_entity_id) if row.related_entity_id else None),
            related_entity_label=(
                str(row.related_entity_label) if row.related_entity_label else None
            ),
            payload_json=(dict(row.payload_json) if isinstance(row.payload_json, dict) else None),
            created_at=row.created_at,
        )


class PaginatedStylebookActivityResponse(BaseModel):
    events: list[StylebookActivityEventOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


@router.get(
    "/{stylebook_slug}/activity",
    response_model=PaginatedStylebookActivityResponse,
)
def list_stylebook_activity(
    stylebook_slug: str,
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedStylebookActivityResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    filters: list[Any] = [StylebookActivity.stylebook_id == int(sb.id)]
    if event_type and event_type.strip():
        filters.append(StylebookActivity.event_type == event_type.strip())
    if entity_type and entity_type.strip():
        filters.append(StylebookActivity.entity_type == entity_type.strip())
    if source and source.strip():
        filters.append(StylebookActivity.source == source.strip())
    if since is not None:
        filters.append(col(StylebookActivity.created_at) >= since)

    total = int(
        session.scalar(select(func.count()).select_from(StylebookActivity).where(*filters)) or 0
    )
    rows = list(
        session.exec(
            select(StylebookActivity)
            .where(*filters)
            .order_by(col(StylebookActivity.created_at).desc(), col(StylebookActivity.id).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    events = [StylebookActivityEventOut.from_row(row) for row in rows if row.id is not None]
    page = offset // limit + 1 if limit else 1
    return PaginatedStylebookActivityResponse(
        events=events,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(events) < total,
        has_prev=offset > 0,
    )
