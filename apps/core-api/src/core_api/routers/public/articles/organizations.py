"""GET /public/v1/projects/{project_slug}/articles/{article_id}/organizations."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import (
    PublicArticleOrganizationOut,
    list_article_organizations,
)
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    NATURE_PARAM_DESCRIPTION,
    parse_natures,
    require_article,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginatedResponse, PaginationOut

router = APIRouter()


@router.get(
    "/{article_id}/organizations",
    response_model=PaginatedResponse[PublicArticleOrganizationOut],
)
def list_project_article_organizations(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    nature: list[str] = Query(
        default=[],
        description=NATURE_PARAM_DESCRIPTION,
    ),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicArticleOrganizationOut]:
    """List organizations mentioned in one article."""
    require_article(session, project, article_id)
    natures = parse_natures(nature)
    items, total = list_article_organizations(
        session,
        article_id=article_id,
        natures=natures,
        quotes_only=quote is True,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
