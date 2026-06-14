"""GET /public/v1/projects/{project_slug}/locations/geo-search."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.location_geo_search import (
    PublicLocationGeoSearchMode,
    PublicLocationGeoSearchParams,
    search_public_locations_by_geo,
)
from backfield_entities.public.locations import PublicLocationOut
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import parse_bbox
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.locations.helpers import resolve_public_locations_scope
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicLocationGeoSearchResponse(BaseModel):
    items: list[PublicLocationOut]
    pagination: PaginationOut
    search_mode: Literal["point", "bbox"]


@router.get("/geo-search", response_model=PublicLocationGeoSearchResponse)
def search_project_locations_by_geo(
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
    q: str | None = Query(None, description="Optional label or address filter"),
    location_type: str | None = Query(None, description="Filter by canonical location type"),
    nature: str | None = Query(
        None,
        description="Filter to locations with at least one linked mention of this nature",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicLocationGeoSearchResponse:
    """Find canonical locations whose geometry intersects a point radius or bounding box."""
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

    if has_bbox:
        min_lng, min_lat, max_lng, max_lat = parse_bbox(bbox)
        params = PublicLocationGeoSearchParams(
            mode=PublicLocationGeoSearchMode.bbox,
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            q=q,
            location_type=location_type,
            nature=nature,
            min_mentions=min_mentions,
            limit=limit,
            offset=offset,
        )
        search_mode: Literal["point", "bbox"] = "bbox"
    else:
        if center_lng is None or center_lat is None or radius_miles is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="center_lng, center_lat, and radius_miles are required together.",
            )
        params = PublicLocationGeoSearchParams(
            mode=PublicLocationGeoSearchMode.point,
            center_lng=center_lng,
            center_lat=center_lat,
            radius_miles=radius_miles,
            q=q,
            location_type=location_type,
            nature=nature,
            min_mentions=min_mentions,
            limit=limit,
            offset=offset,
        )
        search_mode = "point"

    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    items, total = search_public_locations_by_geo(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    return PublicLocationGeoSearchResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
        search_mode=search_mode,
    )
