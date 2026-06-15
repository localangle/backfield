"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}/articles."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.articles import PublicArticleOut
from backfield_entities.public.organizations import (
    get_public_organization,
    list_public_organization_articles,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.organizations.helpers import (
    parse_organization_id,
    resolve_public_organizations_scope,
)
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicOrganizationArticlesOut(BaseModel):
    organization_id: str
    label: str
    items: list[PublicArticleOut]
    pagination: PaginationOut


@router.get("/{organization_id}/articles", response_model=PublicOrganizationArticlesOut)
def list_project_organization_articles(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    nature: str | None = Query(
        None,
        description="Filter to articles with a mention of this editorial nature",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_preview: bool = Query(
        False,
        description="Include a short text preview (max 280 characters) per article",
    ),
) -> PublicOrganizationArticlesOut:
    """Return paginated articles mentioning a canonical organization in this project."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    parsed_id = parse_organization_id(organization_id)
    result = list_public_organization_articles(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
        nature=nature,
        limit=limit,
        offset=offset,
        include_preview=include_preview,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    items, total = result
    organization = get_public_organization(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
    )
    assert organization is not None
    return PublicOrganizationArticlesOut(
        organization_id=organization.id,
        label=organization.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
