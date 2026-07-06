"""GET /public/v1/projects/{project_slug}/articles/geo-search."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_geo_search import (
    PublicArticleGeoSearchMode,
    PublicArticleGeoSearchParams,
    public_article_geo_search_query_out,
    search_public_articles_by_geo,
)
from backfield_entities.public.article_hub import enrich_articles_with_counts
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    INCLUDE_PARAM_DESCRIPTION,
    META_PARAM_DESCRIPTION,
    parse_article_includes,
    parse_bbox,
    parse_location_types,
    parse_optional_date,
    resolve_article_metadata_filters,
)
from core_api.routers.public.articles.responses import PublicArticleGeoSearchOut
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


@router.get("/geo-search", response_model=PublicArticleGeoSearchOut)
def search_project_articles_by_geo(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    center_lng: float | None = Query(None, description="Center longitude for radius search"),
    center_lat: float | None = Query(None, description="Center latitude for radius search"),
    radius_miles: float | None = Query(
        None,
        ge=0,
        description="Search radius in miles (required with center_lng/center_lat)",
    ),
    bbox: str | None = Query(
        None,
        description="Bounding box as min_lng,min_lat,max_lng,max_lat",
    ),
    location_type: list[str] = Query(
        default=[],
        description=(
            "Repeatable location type filter (OR). Include articles with a matching "
            "mention of any listed substrate location_type."
        ),
    ),
    nature: str | None = Query(
        None,
        description=(
            "Filter matching location mentions by editorial nature "
            "(e.g. primary, secondary, historical)"
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
    include: list[str] = Query(default=[], description=INCLUDE_PARAM_DESCRIPTION),
) -> PublicArticleGeoSearchOut:
    """Find articles with location mentions near a point or inside a bounding box."""
    includes = parse_article_includes(include)
    has_center = center_lng is not None and center_lat is not None
    has_bbox = bbox is not None and bbox.strip() != ""
    if has_center and has_bbox:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either center_lng/center_lat/radius_miles or bbox, not both.",
        )
    if not has_center and not has_bbox:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide center_lng/center_lat/radius_miles or bbox.",
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
    pub_date_from_parsed = parse_optional_date(pub_date_from, param_name="pub_date_from")
    pub_date_to_parsed = parse_optional_date(pub_date_to, param_name="pub_date_to")
    location_types = parse_location_types(location_type)

    if has_bbox:
        min_lng, min_lat, max_lng, max_lat = parse_bbox(bbox)
        params = PublicArticleGeoSearchParams(
            mode=PublicArticleGeoSearchMode.bbox,
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            location_types=location_types,
            nature=nature,
            meta_type=resolved_meta_type,
            meta_category=resolved_meta_category,
            exclude_meta_type=resolved_exclude_meta_type,
            exclude_meta_category=resolved_exclude_meta_category,
            meta_clauses=meta_clauses,
            pub_date_from=pub_date_from_parsed,
            pub_date_to=pub_date_to_parsed,
            limit=limit,
            offset=offset,
        )
    else:
        if center_lng is None or center_lat is None or radius_miles is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="center_lng, center_lat, and radius_miles are required together.",
            )
        params = PublicArticleGeoSearchParams(
            mode=PublicArticleGeoSearchMode.point,
            center_lng=center_lng,
            center_lat=center_lat,
            radius_miles=radius_miles,
            location_types=location_types,
            nature=nature,
            meta_type=resolved_meta_type,
            meta_category=resolved_meta_category,
            exclude_meta_type=resolved_exclude_meta_type,
            exclude_meta_category=resolved_exclude_meta_category,
            meta_clauses=meta_clauses,
            pub_date_from=pub_date_from_parsed,
            pub_date_to=pub_date_to_parsed,
            limit=limit,
            offset=offset,
        )

    items, total = search_public_articles_by_geo(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        params=params,
    )
    if "counts" in includes:
        enrich_articles_with_counts(session, items)
    query = public_article_geo_search_query_out(params)
    return PublicArticleGeoSearchOut(
        **query.model_dump(),
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
