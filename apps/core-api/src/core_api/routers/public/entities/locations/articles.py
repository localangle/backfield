"""GET /public/v1/projects/{project_slug}/locations/{location_id}/articles."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.articles import PublicArticleOut
from backfield_entities.public.locations import get_public_location, list_public_location_articles
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.locations.helpers import (
    parse_location_id,
    resolve_public_locations_scope,
)
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicLocationArticlesOut(BaseModel):
    location_id: str
    label: str
    items: list[PublicArticleOut]
    pagination: PaginationOut


@router.get("/{location_id}/articles", response_model=PublicLocationArticlesOut)
def list_project_location_articles(
    location_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    nature: str | None = Query(
        None,
        description="Filter to articles with a mention of this editorial nature",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicLocationArticlesOut:
    """Return paginated articles mentioning a canonical location in this project."""
    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    parsed_id = parse_location_id(location_id)
    result = list_public_location_articles(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=parsed_id,
        nature=nature,
        limit=limit,
        offset=offset,
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
    return PublicLocationArticlesOut(
        location_id=location.id,
        label=location.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
