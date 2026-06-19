"""GET /public/v1/projects/{project_slug}/articles/{article_id}/custom-records."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import (
    PublicArticleCustomRecordOut,
    list_article_custom_records,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import require_article
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get(
    "/{article_id}/custom-records",
    response_model=PaginatedResponse[PublicArticleCustomRecordOut],
)
def list_project_article_custom_records(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    record_type: str | None = Query(
        None,
        description="Filter to one custom record type (e.g. contracts, ingredients)",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicArticleCustomRecordOut]:
    """List custom extracted records for one article."""
    require_article(session, project, article_id)
    items, total = list_article_custom_records(
        session,
        article_id=article_id,
        record_type=record_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
