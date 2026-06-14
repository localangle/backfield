"""GET /public/v1/projects/{project_slug}/locations/{location_id}/mentions."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.locations import (
    PublicLocationMentionOut,
    get_public_location,
    list_public_location_mentions,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.locations.helpers import (
    parse_location_id,
    resolve_public_locations_scope,
)
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicLocationMentionsOut(BaseModel):
    location_id: str
    label: str
    items: list[PublicLocationMentionOut]
    pagination: PaginationOut


@router.get("/{location_id}/mentions", response_model=PublicLocationMentionsOut)
def list_project_location_mentions(
    location_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    sort: Literal["article", "created_at"] = Query("created_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicLocationMentionsOut:
    """Return paginated mention evidence for a canonical location in this project."""
    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    parsed_id = parse_location_id(location_id)
    result = list_public_location_mentions(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=parsed_id,
        limit=limit,
        offset=offset,
        sort=sort,
        sort_direction=sort_direction,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    items, total = result
    location = get_public_location(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=parsed_id,
    )
    assert location is not None
    return PublicLocationMentionsOut(
        location_id=location.id,
        label=location.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
