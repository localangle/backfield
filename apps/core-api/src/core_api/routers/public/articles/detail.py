"""GET /public/v1/projects/{project_slug}/articles/{article_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.articles import PublicArticleOut, get_public_article
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import parse_include
from core_api.routers.public.deps import get_public_project

router = APIRouter()


@router.get("/{article_id}", response_model=PublicArticleOut)
def get_project_article(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    include_preview: bool = Query(
        True,
        description="Include a short text preview (max 280 characters)",
    ),
    include: str | None = Query(
        None,
        description="Optional embeds: counts",
    ),
) -> PublicArticleOut:
    """Return one article by id (no full body text)."""
    include_flags = parse_include(include)
    article = get_public_article(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
        include_preview=include_preview,
        include_counts="counts" in include_flags,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article
