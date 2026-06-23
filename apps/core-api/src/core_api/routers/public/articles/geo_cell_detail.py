"""GET /public/v1/projects/{project_slug}/articles/geo-cells/{h3_cell}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_geo_cell_detail import (
    PublicArticleGeoCellDetailItemOut,
    PublicArticleGeoCellDetailParams,
    search_public_articles_in_cell,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from h3 import is_valid_cell
from pydantic import BaseModel, Field
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    META_PARAM_DESCRIPTION,
    parse_optional_date,
    resolve_article_metadata_filters,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicArticleGeoCellDetailResponse(BaseModel):
    h3_cell: str
    resolution: int
    items: list[PublicArticleGeoCellDetailItemOut] = Field(default_factory=list)
    pagination: PaginationOut


@router.get("/geo-cells/{h3_cell}", response_model=PublicArticleGeoCellDetailResponse)
def list_project_articles_in_geo_cell(
    h3_cell: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    location_type: str | None = Query(None, description="Filter matching locations by type"),
    nature: str | None = Query(
        None,
        description=(
            "Filter matching location mentions by editorial nature (e.g. primary, secondary)"
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
    meta: list[str] = Query(default=[], description=META_PARAM_DESCRIPTION),
    pub_date_from: str | None = Query(
        None,
        description="ISO date YYYY-MM-DD, inclusive lower bound on article pub_date",
    ),
    pub_date_to: str | None = Query(
        None,
        description="ISO date YYYY-MM-DD, inclusive upper bound on article pub_date",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_preview: bool = Query(
        False,
        description="Include a short text preview (max 280 characters) per article",
    ),
) -> PublicArticleGeoCellDetailResponse:
    """Return articles and in-cell location mentions for one H3 coverage cell."""
    normalized_cell = h3_cell.strip()
    if not normalized_cell or not is_valid_cell(normalized_cell):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid h3_cell.",
        )

    (
        resolved_meta_type,
        resolved_meta_category,
        resolved_exclude_meta_type,
        resolved_exclude_meta_category,
        meta_clauses,
    ) = resolve_article_metadata_filters(
        section=section,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        meta=meta,
    )
    params = PublicArticleGeoCellDetailParams(
        h3_cell=normalized_cell,
        location_type=location_type,
        nature=nature,
        meta_type=resolved_meta_type,
        meta_category=resolved_meta_category,
        exclude_meta_type=resolved_exclude_meta_type,
        exclude_meta_category=resolved_exclude_meta_category,
        meta_clauses=meta_clauses,
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        limit=limit,
        offset=offset,
        include_preview=include_preview,
    )
    result = search_public_articles_in_cell(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        params=params,
    )
    return PublicArticleGeoCellDetailResponse(
        h3_cell=result.h3_cell,
        resolution=result.resolution,
        items=result.items,
        pagination=PaginationOut(limit=limit, offset=offset, total=result.total),
    )
