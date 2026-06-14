"""Public canonical location list and search routes."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.locations import PublicLocationOut, search_public_locations
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.locations.helpers import (
    build_location_search_params,
    resolve_public_locations_scope,
)
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


def _search_locations(
    *,
    session: Session,
    project: BackfieldProject,
    q: str | None,
    location_type: str | None,
    nature: str | None,
    min_mentions: int,
    sort: str | None,
    limit: int,
    offset: int,
) -> PaginatedResponse[PublicLocationOut]:
    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    params = build_location_search_params(
        q=q,
        location_type=location_type,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items, total = search_public_locations(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )


@router.get("/", response_model=PaginatedResponse[PublicLocationOut])
def list_project_locations(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    q: str | None = Query(None, description="Search label or formatted address"),
    location_type: str | None = Query(None),
    nature: str | None = Query(
        None,
        description="Filter to locations with at least one linked mention of this nature",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: str | None = Query(
        None,
        description="label (default) or recent",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicLocationOut]:
    """List canonical locations in the project's Stylebook."""
    return _search_locations(
        session=session,
        project=project,
        q=q,
        location_type=location_type,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=PaginatedResponse[PublicLocationOut])
def search_project_locations(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    q: str | None = Query(None, description="Search label or formatted address"),
    location_type: str | None = Query(None),
    nature: str | None = Query(
        None,
        description="Filter to locations with at least one linked mention of this nature",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: str | None = Query(
        None,
        description="label (default) or recent",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicLocationOut]:
    """Search canonical locations by name, address, and filters."""
    return _search_locations(
        session=session,
        project=project,
        q=q,
        location_type=location_type,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )
