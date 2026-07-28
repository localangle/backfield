"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}/mentions."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.mention_timeline import (
    PublicEntityMentionTimelineItemOut,
    list_public_organization_mention_timeline,
)
from backfield_entities.public.organizations import (
    PublicOrganizationMentionOut,
    get_public_organization,
    list_public_organization_mentions,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    META_PARAM_DESCRIPTION,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.mention_helpers import (
    build_entity_mention_list_params,
    build_entity_mention_timeline_params,
)
from core_api.routers.public.entities.organizations.helpers import (
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


class PublicOrganizationMentionTimelineOut(BaseModel):
    organization_id: str
    label: str
    items: list[PublicEntityMentionTimelineItemOut]


@router.get(
    "/{organization_id}/mentions/timeline",
    response_model=PublicOrganizationMentionTimelineOut,
)
def list_project_organization_mention_timeline(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
) -> PublicOrganizationMentionTimelineOut:
    """Return mention counts grouped by article publication date for one organization."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    parsed_id = parse_organization_id(organization_id)
    params = build_entity_mention_timeline_params(
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        quotes_only=quote is True,
    )
    items = list_public_organization_mention_timeline(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
        params=params,
    )
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    organization = get_public_organization(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
    )
    assert organization is not None
    return PublicOrganizationMentionTimelineOut(
        organization_id=organization.id,
        label=organization.label,
        items=items,
    )


@router.get("/{organization_id}/mentions", response_model=PublicOrganizationMentionsOut)
def list_project_organization_mentions(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    sort: Literal["article", "created_at"] = Query("created_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    nature: str | None = Query(None, description="Filter by mention nature"),
    author: str | None = Query(None, description="Filter by article byline (exact match)"),
    external_source: str | None = Query(
        None,
        description="Filter by publication/outlet name (exact match)",
    ),
    meta: list[str] = Query(default=[], description=META_PARAM_DESCRIPTION),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicOrganizationMentionsOut:
    """Return paginated mention evidence for a canonical organization in this project."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    parsed_id = parse_organization_id(organization_id)
    params = build_entity_mention_list_params(
        nature=nature,
        author=author,
        external_source=external_source,
        section=None,
        meta_type=None,
        meta_category=None,
        exclude_meta_type=None,
        exclude_meta_category=None,
        meta_clauses=parse_meta_clauses(meta),
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        quotes_only=quote is True,
        sort=sort,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )
    result = list_public_organization_mentions(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
        params=params,
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
