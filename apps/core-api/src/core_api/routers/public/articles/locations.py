"""GET /public/v1/projects/{project_slug}/articles/{article_id}/locations."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import (
    PublicArticleLocationOut,
    list_article_locations,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import require_article
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get("/{article_id}/locations", response_model=PaginatedResponse[PublicArticleLocationOut])
def list_project_article_locations(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicArticleLocationOut]:
    """List location mentions for one article with geography fields."""
    require_article(session, project, article_id)
    items, total = list_article_locations(
        session,
        article_id=article_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
