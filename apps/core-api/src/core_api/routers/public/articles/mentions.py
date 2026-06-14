"""GET /public/v1/projects/{project_slug}/articles/{article_id}/mentions."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import (
    PublicArticleMentionOut,
    list_article_mentions,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import parse_entity_type, require_article
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get("/{article_id}/mentions", response_model=PaginatedResponse[PublicArticleMentionOut])
def list_project_article_mentions(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    entity_type: str | None = Query(
        None,
        description="Filter by entity type: location, person, organization",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicArticleMentionOut]:
    """List mention evidence for one article across entity types."""
    require_article(session, project, article_id)
    parsed_type = parse_entity_type(entity_type)
    items, total = list_article_mentions(
        session,
        article_id=article_id,
        entity_type=parsed_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
