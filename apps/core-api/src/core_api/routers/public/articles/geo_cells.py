"""GET /public/v1/projects/{project_slug}/articles/geo-cells."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_geo_cells import (
    PublicArticleGeoCellsParams,
    PublicArticleGeoCellsResult,
    PublicArticleGeoCellsTooManyError,
    aggregate_article_geo_cells,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import parse_bbox, parse_optional_date
from core_api.routers.public.deps import get_public_project

router = APIRouter()


@router.get("/geo-cells", response_model=PublicArticleGeoCellsResult)
def aggregate_project_articles_by_geo_cells(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    bbox: str = Query(..., description="Bounding box as min_lng,min_lat,max_lng,max_lat"),
    resolution: int | None = Query(
        None,
        ge=0,
        le=15,
        description=(
            "Optional H3 display resolution. When omitted, derived from bbox viewport size."
        ),
    ),
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
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
) -> PublicArticleGeoCellsResult:
    """Return H3 cells with distinct-article counts for location mentions in a bounding box."""
    min_lng, min_lat, max_lng, max_lat = parse_bbox(bbox)
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox must have min_lng < max_lng and min_lat < max_lat.",
        )

    params = PublicArticleGeoCellsParams(
        min_lng=min_lng,
        min_lat=min_lat,
        max_lng=max_lng,
        max_lat=max_lat,
        resolution=resolution,
        location_type=location_type,
        nature=nature,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
    )
    try:
        return aggregate_article_geo_cells(
            session,
            project_id=int(project.id),  # type: ignore[arg-type]
            params=params,
        )
    except PublicArticleGeoCellsTooManyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
