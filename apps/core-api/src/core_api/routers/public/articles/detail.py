"""GET /public/v1/projects/{project_slug}/articles/{article_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import (
    enrich_articles_with_counts,
    inline_article_images,
)
from backfield_entities.public.articles import PublicArticleOut, get_public_article
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    INCLUDE_PARAM_DESCRIPTION,
    parse_article_includes,
)
from core_api.routers.public.deps import get_public_project

router = APIRouter()


@router.get("/{article_id}", response_model=PublicArticleOut)
def get_project_article(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    include: list[str] = Query(default=[], description=INCLUDE_PARAM_DESCRIPTION),
) -> PublicArticleOut:
    """Return one article by id (no full body text)."""
    includes = parse_article_includes(include)
    article = get_public_article(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.images = inline_article_images(session, article_id=article_id)
    if "counts" in includes:
        enrich_articles_with_counts(session, [article])
    return article
