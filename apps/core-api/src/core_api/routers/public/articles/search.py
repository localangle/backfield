"""GET /public/v1/projects/{project_slug}/articles/search."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.articles import (
    PublicArticleOut,
    PublicArticleSearchParams,
    search_public_articles,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    parse_has_mentions,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get("/search", response_model=PaginatedResponse[PublicArticleOut])
def search_project_articles(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    q: str | None = Query(
        None,
        description=(
            "Keyword match on headline, body text, or URL. On PostgreSQL supports "
            'quoted phrases ("…"), OR, and - exclusions (web search syntax).'
        ),
    ),
    meta_type: str | None = Query(None, description="Include articles with this metadata type"),
    meta_category: str | None = Query(
        None,
        description="With meta_type, include articles with this metadata category",
    ),
    exclude_meta_type: str | None = Query(
        None,
        description="Exclude articles with a metadata row of this type",
    ),
    exclude_meta_category: str | None = Query(
        None,
        description="With exclude_meta_type, exclude articles with this metadata category",
    ),
    section: str | None = Query(
        None,
        description="Include articles with this subject metadata category (editorial section)",
    ),
    author: str | None = Query(None, description="Filter by byline (case-insensitive exact match)"),
    external_source: str | None = Query(
        None,
        description="Filter by publication/outlet name (case-insensitive exact match)",
    ),
    source: str | None = Query(
        None,
        description="Alias for external_source",
        deprecated=True,
    ),
    has_mentions: str | None = Query(
        None,
        description="Require mentions of location, person, or organization",
    ),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_preview: bool = Query(
        False,
        description="Include a short text preview (max 280 characters) per article",
    ),
    meta: list[str] = Query(
        default=[],
        description=(
            "Repeatable metadata filter clause (AND across clauses). "
            "Forms: type, type:category, type:cat1|cat2 (OR within type), !type or !type:category."
        ),
    ),
) -> PaginatedResponse[PublicArticleOut]:
    """Search project articles by keyword, metadata tags, and publication date."""
    outlet = external_source or source
    params = PublicArticleSearchParams(
        q=q,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        section=section,
        meta_clauses=parse_meta_clauses(meta),
        author=author,
        external_source=outlet,
        has_mentions=parse_has_mentions(has_mentions),
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        limit=limit,
        offset=offset,
        include_preview=include_preview,
    )
    items, total = search_public_articles(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        params=params,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
