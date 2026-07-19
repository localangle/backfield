"""GET /public/v1/projects/{project_slug}/articles/search."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import enrich_articles_with_counts
from backfield_entities.public.articles import (
    PublicArticleSearchParams,
    PublicArticleSort,
    PublicSortDirection,
    public_article_search_query_out,
    resolve_public_article_search_params,
    search_public_articles,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    INCLUDE_PARAM_DESCRIPTION,
    META_PARAM_DESCRIPTION,
    parse_article_includes,
    parse_has_mentions,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.articles.responses import PublicArticleSearchOut
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


@router.get("/search", response_model=PublicArticleSearchOut)
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
    author: str | None = Query(None, description="Filter by byline (case-insensitive exact match)"),
    external_source: str | None = Query(
        None,
        description="Filter by publication/outlet name (case-insensitive exact match)",
    ),
    has_mentions: str | None = Query(
        None,
        description="Require mentions of location, person, or organization",
    ),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    sort: PublicArticleSort | None = Query(
        None,
        description="Sort by relevance or publication date",
    ),
    sort_direction: PublicSortDirection | None = Query(
        None,
        description="Sort direction; defaults to descending",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include: list[str] = Query(default=[], description=INCLUDE_PARAM_DESCRIPTION),
    meta: list[str] = Query(default=[], description=META_PARAM_DESCRIPTION),
) -> PublicArticleSearchOut:
    """Search project articles by keyword, metadata tags, and publication date."""
    if sort is PublicArticleSort.relevance and not (q or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort=relevance requires a non-empty q.",
        )
    includes = parse_article_includes(include)
    params = resolve_public_article_search_params(
        PublicArticleSearchParams(
            q=q,
            meta_clauses=parse_meta_clauses(meta),
            author=author,
            external_source=external_source,
            has_mentions=parse_has_mentions(has_mentions),
            pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
            pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
            sort=sort,
            sort_direction=sort_direction,
            limit=limit,
            offset=offset,
        )
    )
    items, total = search_public_articles(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        params=params,
    )
    if "counts" in includes:
        enrich_articles_with_counts(session, items)
    query = public_article_search_query_out(params)
    return PublicArticleSearchOut(
        **query.model_dump(),
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
