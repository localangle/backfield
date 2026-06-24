"""Geographic canonical location search via Stylebook geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backfield_db import StylebookLocationCanonical
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.public.article_geo_search import (
    MILES_TO_METERS,
    _haversine_miles,
    _point_coordinates,
    _sqlite_geometry_matches,
)
from backfield_entities.public.locations import (
    PublicLocationOut,
    PublicLocationSearchParams,
    _location_to_public_out,
    _mention_counts_by_canonical,
    _story_counts_by_canonical,
    location_filters,
)
from backfield_entities.public.stylebook_scope import stylebook_slugs_by_id


class PublicLocationGeoSearchMode(StrEnum):
    point = "point"
    bbox = "bbox"


@dataclass(frozen=True)
class PublicLocationGeoSearchParams:
    mode: PublicLocationGeoSearchMode
    center_lng: float | None = None
    center_lat: float | None = None
    radius_miles: float | None = None
    min_lng: float | None = None
    min_lat: float | None = None
    max_lng: float | None = None
    max_lat: float | None = None
    q: str | None = None
    location_type: str | None = None
    nature: str | None = None
    min_mentions: int = 0
    limit: int = 25
    offset: int = 0


def _keyword_params_from_geo(params: PublicLocationGeoSearchParams) -> PublicLocationSearchParams:
    return PublicLocationSearchParams(
        q=params.q,
        location_type=params.location_type,
        nature=params.nature,
        min_mentions=params.min_mentions,
        limit=params.limit,
        offset=params.offset,
    )


def _sqlite_geo_rows(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicLocationGeoSearchParams,
) -> list[StylebookLocationCanonical]:
    keyword_params = _keyword_params_from_geo(params)
    filters = location_filters(
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=keyword_params,
    )
    rows = list(session.exec(select(StylebookLocationCanonical).where(*filters)).all())
    article_geo_params = _article_geo_params_from_location_geo(params)
    matching = [
        row
        for row in rows
        if _sqlite_geometry_matches(row.geometry_json, params=article_geo_params)
    ]
    if params.mode is PublicLocationGeoSearchMode.point:
        assert params.center_lng is not None
        assert params.center_lat is not None
        matching.sort(
            key=lambda row: _sqlite_point_distance_miles(
                row.geometry_json,
                center_lng=params.center_lng,
                center_lat=params.center_lat,
            )
        )
    else:
        matching.sort(key=lambda row: (row.label.lower(), str(row.id)))
    return matching


def _article_geo_params_from_location_geo(params: PublicLocationGeoSearchParams):
    from backfield_entities.public.article_geo_search import (
        PublicArticleGeoSearchMode,
        PublicArticleGeoSearchParams,
    )

    mode = (
        PublicArticleGeoSearchMode.point
        if params.mode is PublicLocationGeoSearchMode.point
        else PublicArticleGeoSearchMode.bbox
    )
    if params.mode is PublicLocationGeoSearchMode.point:
        return PublicArticleGeoSearchParams(
            mode=mode,
            center_lng=params.center_lng,
            center_lat=params.center_lat,
            radius_miles=params.radius_miles,
        )
    return PublicArticleGeoSearchParams(
        mode=mode,
        min_lng=params.min_lng,
        min_lat=params.min_lat,
        max_lng=params.max_lng,
        max_lat=params.max_lat,
    )


def _sqlite_point_distance_miles(
    geometry_json: dict | None,
    *,
    center_lng: float,
    center_lat: float,
) -> float:
    point = _point_coordinates(geometry_json)
    if point is None:
        return float("inf")
    lng, lat = point
    return _haversine_miles(center_lng, center_lat, lng, lat)


def _postgres_geo_ids(
    session: Session,
    *,
    stylebook_id: int,
    params: PublicLocationGeoSearchParams,
) -> list[str]:
    bind: dict[str, object] = {"stylebook_id": stylebook_id}
    if params.mode is PublicLocationGeoSearchMode.point:
        assert params.center_lng is not None
        assert params.center_lat is not None
        assert params.radius_miles is not None
        bind["center_lng"] = params.center_lng
        bind["center_lat"] = params.center_lat
        bind["radius_meters"] = params.radius_miles * MILES_TO_METERS
        area_cte = """
        WITH search_area AS (
            SELECT ST_Buffer(
                ST_SetSRID(ST_MakePoint(:center_lng, :center_lat), 4326)::geography,
                :radius_meters
            ) AS geom
        )
        """
        order_sql = """
        ORDER BY ST_Distance(
            slc.geometry::geography,
            ST_SetSRID(ST_MakePoint(:center_lng, :center_lat), 4326)::geography
        ),
        lower(slc.label),
        slc.id
        """
    else:
        assert params.min_lng is not None
        assert params.min_lat is not None
        assert params.max_lng is not None
        assert params.max_lat is not None
        bind.update(
            {
                "min_lng": params.min_lng,
                "min_lat": params.min_lat,
                "max_lng": params.max_lng,
                "max_lat": params.max_lat,
            }
        )
        area_cte = """
        WITH search_area AS (
            SELECT ST_SetSRID(
                ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326),
                4326
            )::geography AS geom
        )
        """
        order_sql = "ORDER BY lower(slc.label), slc.id"

    location_type_filter = ""
    if (params.location_type or "").strip():
        bind["location_type"] = params.location_type.strip()
        location_type_filter = "AND slc.location_type = :location_type"

    q_filter = ""
    if (params.q or "").strip():
        bind["q"] = f"%{(params.q or '').strip()}%"
        q_filter = """
        AND (
            slc.label ILIKE :q
            OR slc.formatted_address ILIKE :q
        )
        """

    stmt = text(
        area_cte
        + """
        SELECT slc.id
        FROM stylebook_location_canonical slc
        CROSS JOIN search_area sa
        WHERE slc.stylebook_id = :stylebook_id
          AND slc.status = 'active'
          AND slc.geometry IS NOT NULL
          AND ST_DWithin(slc.geometry::geography, sa.geom, 0)
        """
        + location_type_filter
        + q_filter
        + order_sql
    )
    rows = session.exec(stmt.bindparams(**bind)).all()
    return [str(row.id) for row in rows]


def search_public_locations_by_geo(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicLocationGeoSearchParams,
) -> tuple[list[PublicLocationOut], int]:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        geo_ids = _postgres_geo_ids(session, stylebook_id=stylebook_id, params=params)
        if not geo_ids:
            return [], 0
        filters = location_filters(
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationSearchParams(
                q=params.q,
                location_type=params.location_type,
                nature=params.nature,
                min_mentions=params.min_mentions,
                limit=10_000,
                offset=0,
            ),
        )
        filters.append(col(StylebookLocationCanonical.id).in_(geo_ids))
        rows = list(session.exec(select(StylebookLocationCanonical).where(*filters)).all())
        order_index = {cid: idx for idx, cid in enumerate(geo_ids)}
        rows.sort(key=lambda row: order_index.get(str(row.id), 10_000_000))
    else:
        rows = _sqlite_geo_rows(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=params,
        )

    total = len(rows)
    page_rows = rows[params.offset : params.offset + params.limit]
    canonical_ids = [str(row.id) for row in page_rows if row.id is not None]
    mention_counts = _mention_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=canonical_ids,
    )
    story_counts = _story_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=canonical_ids,
    )
    stylebook_slug = stylebook_slugs_by_id(session, {stylebook_id}).get(stylebook_id)
    items = [
        _location_to_public_out(
            row,
            mention_count=mention_counts.get(str(row.id), 0),
            story_count=story_counts.get(str(row.id), 0),
            stylebook_slug=stylebook_slug,
        )
        for row in page_rows
    ]
    return items, total
