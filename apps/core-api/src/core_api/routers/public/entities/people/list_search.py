"""Public canonical people list and search routes."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.people import PublicPersonOut, search_public_people
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.people.helpers import (
    build_person_search_params,
    resolve_public_people_scope,
)
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut
from core_api.routers.public.stylebook_query import StylebookSlugQuery

router = APIRouter()


def _search_people(
    *,
    session: Session,
    project: BackfieldProject,
    stylebook_slug: str | None,
    q: str | None,
    person_type: str | None,
    public_figure: bool | None,
    title: str | None,
    affiliation: str | None,
    nature: str | None,
    min_mentions: int,
    sort: str | None,
    limit: int,
    offset: int,
) -> PaginatedResponse[PublicPersonOut]:
    stylebook_id, project_id = resolve_public_people_scope(
        session, project, stylebook_slug=stylebook_slug
    )
    params = build_person_search_params(
        q=q,
        person_type=person_type,
        public_figure=public_figure,
        title=title,
        affiliation=affiliation,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items, total = search_public_people(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )


@router.get("/", response_model=PaginatedResponse[PublicPersonOut])
def list_project_people(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = Query(None, description="Search name, title, or affiliation"),
    person_type: str | None = Query(None),
    public_figure: bool | None = Query(None),
    title: str | None = Query(None, description="Case-insensitive substring match on title"),
    affiliation: str | None = Query(
        None,
        description="Case-insensitive substring match on affiliation",
    ),
    nature: str | None = Query(
        None,
        description="Filter to people with at least one linked mention of this nature",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: str | None = Query(
        None,
        description="sort_key (default), recent, or label",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicPersonOut]:
    """List canonical people in the project's Stylebook."""
    return _search_people(
        session=session,
        project=project,
        stylebook_slug=stylebook_slug,
        q=q,
        person_type=person_type,
        public_figure=public_figure,
        title=title,
        affiliation=affiliation,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=PaginatedResponse[PublicPersonOut])
def search_project_people(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = Query(None, description="Search name, title, or affiliation"),
    person_type: str | None = Query(None),
    public_figure: bool | None = Query(None),
    title: str | None = Query(None, description="Case-insensitive substring match on title"),
    affiliation: str | None = Query(
        None,
        description="Case-insensitive substring match on affiliation",
    ),
    nature: str | None = Query(
        None,
        description="Filter to people with at least one linked mention of this nature",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: str | None = Query(
        None,
        description="sort_key (default), recent, or label",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicPersonOut]:
    """Search canonical people by name, title, affiliation, and filters."""
    return _search_people(
        session=session,
        project=project,
        stylebook_slug=stylebook_slug,
        q=q,
        person_type=person_type,
        public_figure=public_figure,
        title=title,
        affiliation=affiliation,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort,
        limit=limit,
        offset=offset,
    )
