"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}/mentions."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.organizations import (
    PublicOrganizationMentionOut,
    get_public_organization,
    list_public_organization_mentions,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.organizations.helpers import (
    parse_organization_id,
    resolve_public_organizations_scope,
)
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicOrganizationMentionsOut(BaseModel):
    organization_id: str
    label: str
    items: list[PublicOrganizationMentionOut]
    pagination: PaginationOut


@router.get("/{organization_id}/mentions", response_model=PublicOrganizationMentionsOut)
def list_project_organization_mentions(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    sort: Literal["article", "created_at"] = Query("created_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicOrganizationMentionsOut:
    """Return paginated mention evidence for a canonical organization in this project."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    parsed_id = parse_organization_id(organization_id)
    result = list_public_organization_mentions(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
        limit=limit,
        offset=offset,
        sort=sort,
        sort_direction=sort_direction,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    items, total = result
    organization = get_public_organization(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
    )
    assert organization is not None
    return PublicOrganizationMentionsOut(
        organization_id=organization.id,
        label=organization.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
