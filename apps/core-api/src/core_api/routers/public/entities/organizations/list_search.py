"""Public canonical organization list and search routes."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.organizations import (
    PublicOrganizationOut,
    search_public_organizations,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    ATTR_PARAM_DESCRIPTION,
    ENTITY_INCLUDE_PARAM_DESCRIPTION,
    NATURE_PARAM_DESCRIPTION,
    parse_attr_clauses_or_400,
    parse_entity_includes,
    parse_natures,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.organizations.helpers import (
    build_organization_search_params,
    resolve_public_organizations_scope,
)
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut
from core_api.routers.public.stylebook_query import StylebookSlugQuery

router = APIRouter()


def _search_organizations(
    *,
    session: Session,
    project: BackfieldProject,
    stylebook_slug: str | None,
    q: str | None,
    organization_type: str | None,
    natures: tuple[str, ...],
    min_mentions: int,
    attr: list[str],
    include: list[str],
    sort: str | None,
    limit: int,
    offset: int,
) -> PaginatedResponse[PublicOrganizationOut]:
    stylebook_id, project_id = resolve_public_organizations_scope(
        session, project, stylebook_slug=stylebook_slug
    )
    includes = parse_entity_includes(include)
    params = build_organization_search_params(
        q=q,
        organization_type=organization_type,
        natures=natures,
        min_mentions=min_mentions,
        attr_clauses=parse_attr_clauses_or_400(attr),
        include_metadata="metadata" in includes,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items, total = search_public_organizations(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )


@router.get("/", response_model=PaginatedResponse[PublicOrganizationOut])
def list_project_organizations(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = Query(None, description="Search organization name"),
    organization_type: str | None = Query(None),
    nature: list[str] = Query(
        default=[],
        description=NATURE_PARAM_DESCRIPTION,
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    attr: list[str] = Query(default=[], description=ATTR_PARAM_DESCRIPTION),
    include: list[str] = Query(default=[], description=ENTITY_INCLUDE_PARAM_DESCRIPTION),
    sort: str | None = Query(
        None,
        description="label (default) or recent",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicOrganizationOut]:
    """List canonical organizations in the project's Stylebook."""
    natures = parse_natures(nature)
    return _search_organizations(
        session=session,
        project=project,
        stylebook_slug=stylebook_slug,
        q=q,
        organization_type=organization_type,
        natures=natures,
        min_mentions=min_mentions,
        attr=attr,
        include=include,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=PaginatedResponse[PublicOrganizationOut])
def search_project_organizations(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = Query(None, description="Search organization name"),
    organization_type: str | None = Query(None),
    nature: list[str] = Query(
        default=[],
        description=NATURE_PARAM_DESCRIPTION,
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    attr: list[str] = Query(default=[], description=ATTR_PARAM_DESCRIPTION),
    include: list[str] = Query(default=[], description=ENTITY_INCLUDE_PARAM_DESCRIPTION),
    sort: str | None = Query(
        None,
        description="label (default) or recent",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicOrganizationOut]:
    """Search canonical organizations by name and filters."""
    natures = parse_natures(nature)
    return _search_organizations(
        session=session,
        project=project,
        stylebook_slug=stylebook_slug,
        q=q,
        organization_type=organization_type,
        natures=natures,
        min_mentions=min_mentions,
        attr=attr,
        include=include,
        sort=sort,
        limit=limit,
        offset=offset,
    )
