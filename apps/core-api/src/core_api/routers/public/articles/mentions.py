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

router = APIRouter()


@router.get("/{article_id}/mentions", response_model=list[PublicArticleMentionOut])
def list_project_article_mentions(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    entity_type: str | None = Query(
        None,
        description="Filter by entity type: location, person, organization",
    ),
    nature: str | None = Query(
        None,
        description="Filter to mentions with this editorial nature (e.g. primary, subject, actor)",
    ),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
) -> list[PublicArticleMentionOut]:
    """List mention evidence for one article across entity types."""
    require_article(session, project, article_id)
    parsed_type = parse_entity_type(entity_type)
    return list_article_mentions(
        session,
        article_id=article_id,
        entity_type=parsed_type,
        nature=nature,
        quotes_only=quote is True,
    )
