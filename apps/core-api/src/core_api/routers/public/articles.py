"""Public article read routes."""

from __future__ import annotations

from datetime import date

from backfield_db import BackfieldProject
from backfield_entities.public.articles import (
    PublicArticleOut,
    PublicArticleSearchParams,
    get_public_article,
    search_public_articles,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter(prefix="/projects/{project_slug}/articles", tags=["public-articles"])


def _parse_optional_date(value: str | None, *, param_name: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {param_name}. Use YYYY-MM-DD.",
        ) from exc


@router.get("/search", response_model=PaginatedResponse[PublicArticleOut])
def search_project_articles(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    q: str | None = Query(None, description="Keyword match on headline or URL"),
    meta_type: str | None = Query(None),
    meta_category: str | None = Query(None),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_preview: bool = Query(
        False,
        description="Include a short text preview (max 280 characters) per article",
    ),
) -> PaginatedResponse[PublicArticleOut]:
    """Search project articles by keyword, metadata tags, and publication date."""
    params = PublicArticleSearchParams(
        q=q,
        meta_type=meta_type,
        meta_category=meta_category,
        pub_date_from=_parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=_parse_optional_date(pub_date_to, param_name="pub_date_to"),
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


@router.get("/{article_id}", response_model=PublicArticleOut)
def get_project_article(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    include_preview: bool = Query(
        True,
        description="Include a short text preview (max 280 characters)",
    ),
) -> PublicArticleOut:
    """Return one article by id (no full body text)."""
    article = get_public_article(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
        include_preview=include_preview,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article
