"""GET /public/v1/projects/{project_slug}/mentions/search."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.mentions import (
    PublicMentionSearchItemOut,
    search_public_mentions,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    META_PARAM_DESCRIPTION,
    parse_entity_type,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.mentions.helpers import (
    build_mention_search_params,
    resolve_public_mentions_scope,
)
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get("/search", response_model=PaginatedResponse[PublicMentionSearchItemOut])
def search_project_mentions(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    entity_type: str | None = Query(
        None,
        description="Filter to location, person, or organization mentions",
    ),
    q: str | None = Query(None, description="Keyword match on entity name"),
    nature: str | None = Query(None, description="Filter by mention nature"),
    has_canonical: bool | None = Query(
        None,
        description="When true, only mentions linked to a canonical; when false, only unlinked",
    ),
    author: str | None = Query(None, description="Filter by article byline (exact match)"),
    external_source: str | None = Query(
        None,
        description="Filter by publication/outlet name (exact match)",
    ),
    source: str | None = Query(
        None,
        description="Alias for external_source",
        deprecated=True,
    ),
    section: str | None = Query(
        None,
        description="Include mentions in articles with this subject metadata category",
    ),
    meta_type: str | None = Query(
        None,
        description="Include mentions in articles with this metadata type",
    ),
    meta_category: str | None = Query(
        None,
        description="With meta_type, include mentions in articles with this metadata category",
    ),
    exclude_meta_type: str | None = Query(
        None,
        description="Exclude mentions in articles with a metadata row of this type",
    ),
    exclude_meta_category: str | None = Query(
        None,
        description="With exclude_meta_type, exclude mentions in articles with this category",
    ),
    meta: list[str] = Query(default=[], description=META_PARAM_DESCRIPTION),
    location_type: str | None = Query(
        None,
        description="Filter location mentions by location type",
    ),
    person_type: str | None = Query(None, description="Filter person mentions by person type"),
    organization_type: str | None = Query(
        None,
        description="Filter organization mentions by organization type",
    ),
    public_figure: bool | None = Query(
        None,
        description="Filter person mentions by public figure flag",
    ),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicMentionSearchItemOut]:
    """Search project mentions across articles by entity name, nature, and article filters."""
    outlet = external_source or source
    params = build_mention_search_params(
        entity_type=parse_entity_type(entity_type),
        q=q,
        nature=nature,
        has_canonical=has_canonical,
        author=author,
        external_source=outlet,
        section=section,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        meta_clauses=parse_meta_clauses(meta),
        location_type=location_type,
        person_type=person_type,
        organization_type=organization_type,
        public_figure=public_figure,
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        limit=limit,
        offset=offset,
    )
    project_id = resolve_public_mentions_scope(project)
    items, total = search_public_mentions(session, project_id=project_id, params=params)
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
