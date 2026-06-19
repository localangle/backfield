"""H3 hex-cell article coverage aggregation for the public API."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateLocation, SubstrateLocationMention
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.geo.h3_index import EARTH_RADIUS_KM, POINT_H3_RESOLUTION
from backfield_entities.public.articles import _apply_public_article_list_filters

MAX_CELLS_PER_RESPONSE = 5000
MIN_H3_RESOLUTION = 0

# Viewport characteristic size (km) -> default display resolution when no override.
_BBOX_EXTENT_RESOLUTION_THRESHOLDS_KM: tuple[tuple[float, int], ...] = (
    (50.0, 4),
    (10.0, 5),
    (3.0, 6),
    (1.0, 7),
    (0.3, 8),
    (0.1, 9),
    (0.03, 10),
)


class PublicArticleGeoCellsTooManyError(Exception):
    """Raised when aggregation cannot satisfy the cell ceiling even at minimum resolution."""


@dataclass(frozen=True)
class PublicArticleGeoCellsParams:
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float
    resolution: int | None = None
    location_type: str | None = None
    nature: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None


class PublicArticleGeoCellOut(BaseModel):
    h3_cell: str
    article_count: int


class PublicArticleGeoCellsResult(BaseModel):
    resolution: int
    derived_resolution: int
    requested_resolution: int | None = None
    bbox_extent_km: float
    coarsened: bool = False
    cells: list[PublicArticleGeoCellOut] = Field(default_factory=list)


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bbox_viewport_extent_km(
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
) -> float:
    """Characteristic viewport size in km (geometric mean of width and height)."""
    width_km = _haversine_km(min_lng, min_lat, max_lng, min_lat)
    height_km = _haversine_km(min_lng, min_lat, min_lng, max_lat)
    if width_km <= 0 or height_km <= 0:
        return 0.0
    return math.sqrt(width_km * height_km)


def resolution_for_bbox(
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
) -> int:
    """Derive the default display resolution from viewport size."""
    extent_km = bbox_viewport_extent_km(min_lng, min_lat, max_lng, max_lat)
    for min_extent_km, resolution in _BBOX_EXTENT_RESOLUTION_THRESHOLDS_KM:
        if extent_km > min_extent_km:
            return resolution
    return POINT_H3_RESOLUTION


def initial_resolution(
    *,
    derived_resolution: int,
    resolution_override: int | None,
) -> int:
    """Pick the starting display resolution before auto-coarsen."""
    if resolution_override is None:
        return derived_resolution
    return resolution_override


def _point_coordinates(geometry_json: dict | None) -> tuple[float, float] | None:
    if not isinstance(geometry_json, dict):
        return None
    geom_type = geometry_json.get("type")
    coordinates = geometry_json.get("coordinates")
    if geom_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return float(coordinates[0]), float(coordinates[1])
    return None


def _point_in_bbox(
    lng: float,
    lat: float,
    *,
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
) -> bool:
    return min_lng <= lng <= max_lng and min_lat <= lat <= max_lat


def _allowed_article_ids(
    session: Session,
    *,
    project_id: int,
    candidate_article_ids: set[int],
    params: PublicArticleGeoCellsParams,
) -> set[int]:
    if not candidate_article_ids:
        return set()
    stmt = select(SubstrateArticle.id).where(
        col(SubstrateArticle.id).in_(candidate_article_ids),
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    )
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    return {int(aid) for aid in session.exec(stmt).all()}


def _parent_cell(h3_cell: str, resolution: int) -> str:
    from h3 import cell_to_parent

    return str(cell_to_parent(h3_cell, resolution))


def _aggregate_cell_counts(
    rows: list[tuple[int, str, int]],
    *,
    allowed_article_ids: set[int],
    resolution: int,
) -> dict[str, int]:
    articles_by_cell: dict[str, set[int]] = {}
    for article_id, h3_cell, h3_resolution in rows:
        if article_id not in allowed_article_ids:
            continue
        if h3_resolution < resolution:
            continue
        if h3_resolution == resolution:
            parent = h3_cell
        else:
            parent = _parent_cell(h3_cell, resolution)
        articles_by_cell.setdefault(parent, set()).add(article_id)
    return {cell: len(article_ids) for cell, article_ids in articles_by_cell.items()}


def _aggregate_with_auto_coarsen(
    rows: list[tuple[int, str, int]],
    *,
    allowed_article_ids: set[int],
    starting_resolution: int,
) -> tuple[dict[str, int], int, bool]:
    resolution = starting_resolution
    coarsened = False
    while resolution >= MIN_H3_RESOLUTION:
        counts = _aggregate_cell_counts(
            rows,
            allowed_article_ids=allowed_article_ids,
            resolution=resolution,
        )
        if len(counts) <= MAX_CELLS_PER_RESPONSE:
            return counts, resolution, coarsened
        if resolution == MIN_H3_RESOLUTION:
            break
        resolution -= 1
        coarsened = True
    raise PublicArticleGeoCellsTooManyError(
        f"Aggregation still exceeds {MAX_CELLS_PER_RESPONSE} cells at resolution "
        f"{MIN_H3_RESOLUTION}."
    )


def _postgres_candidate_rows(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellsParams,
) -> list[tuple[int, str, int]]:
    bind: dict[str, object] = {
        "project_id": project_id,
        "min_lng": params.min_lng,
        "min_lat": params.min_lat,
        "max_lng": params.max_lng,
        "max_lat": params.max_lat,
    }
    location_type_filter = ""
    if (params.location_type or "").strip():
        bind["location_type"] = params.location_type.strip()
        location_type_filter = "AND sl.location_type = :location_type"
    nature_filter = ""
    if (params.nature or "").strip():
        bind["nature"] = params.nature.strip()
        nature_filter = "AND lm.nature = :nature"

    stmt = text(
        """
        WITH search_area AS (
            SELECT ST_SetSRID(
                ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326),
                4326
            )::geography AS geom
        )
        SELECT lm.article_id, sl.h3_cell, sl.h3_resolution
        FROM substrate_location_mention lm
        INNER JOIN substrate_article a ON a.id = lm.article_id
        INNER JOIN substrate_location sl ON sl.id = lm.location_id
        CROSS JOIN search_area sa
        WHERE a.project_id = :project_id
          AND a.deleted = false
          AND lm.deleted = false
          AND sl.geometry IS NOT NULL
          AND sl.h3_cell IS NOT NULL
          AND sl.h3_resolution IS NOT NULL
          AND ST_DWithin(sl.geometry::geography, sa.geom, 0)
        """
        + location_type_filter
        + nature_filter
    )
    rows = session.exec(stmt.bindparams(**bind)).all()
    out: list[tuple[int, str, int]] = []
    for row in rows:
        h3_cell = row.h3_cell
        h3_resolution = row.h3_resolution
        if h3_cell is None or h3_resolution is None:
            continue
        out.append((int(row.article_id), str(h3_cell), int(h3_resolution)))
    return out


def _sqlite_candidate_rows(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellsParams,
) -> list[tuple[int, str, int]]:
    stmt = (
        select(SubstrateLocationMention, SubstrateLocation, SubstrateArticle)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
    )
    location_type = (params.location_type or "").strip()
    if location_type:
        stmt = stmt.where(SubstrateLocation.location_type == location_type)
    nature = (params.nature or "").strip()
    if nature:
        stmt = stmt.where(SubstrateLocationMention.nature == nature)

    rows: list[tuple[int, str, int]] = []
    for mention, loc, _article in session.exec(stmt).all():
        if mention.article_id is None or loc.h3_cell is None or loc.h3_resolution is None:
            continue
        point = _point_coordinates(loc.geometry_json)
        if point is None:
            continue
        lng, lat = point
        if not _point_in_bbox(
            lng,
            lat,
            min_lng=params.min_lng,
            min_lat=params.min_lat,
            max_lng=params.max_lng,
            max_lat=params.max_lat,
        ):
            continue
        rows.append((int(mention.article_id), str(loc.h3_cell), int(loc.h3_resolution)))
    return rows


def _build_result(
    counts: dict[str, int],
    *,
    resolution: int,
    derived_resolution: int,
    requested_resolution: int | None,
    bbox_extent_km: float,
    coarsened: bool,
) -> PublicArticleGeoCellsResult:
    cells = [
        PublicArticleGeoCellOut(h3_cell=cell, article_count=count)
        for cell, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return PublicArticleGeoCellsResult(
        resolution=resolution,
        derived_resolution=derived_resolution,
        requested_resolution=requested_resolution,
        bbox_extent_km=round(bbox_extent_km, 3),
        coarsened=coarsened,
        cells=cells,
    )


def aggregate_article_geo_cells(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellsParams,
) -> PublicArticleGeoCellsResult:
    bbox_extent_km = bbox_viewport_extent_km(
        params.min_lng,
        params.min_lat,
        params.max_lng,
        params.max_lat,
    )
    derived_resolution = resolution_for_bbox(
        params.min_lng,
        params.min_lat,
        params.max_lng,
        params.max_lat,
    )
    starting_resolution = initial_resolution(
        derived_resolution=derived_resolution,
        resolution_override=params.resolution,
    )

    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        candidate_rows = _postgres_candidate_rows(session, project_id=project_id, params=params)
    else:
        candidate_rows = _sqlite_candidate_rows(session, project_id=project_id, params=params)

    candidate_article_ids = {article_id for article_id, _, _ in candidate_rows}
    allowed_article_ids = _allowed_article_ids(
        session,
        project_id=project_id,
        candidate_article_ids=candidate_article_ids,
        params=params,
    )
    counts, resolution, coarsened = _aggregate_with_auto_coarsen(
        candidate_rows,
        allowed_article_ids=allowed_article_ids,
        starting_resolution=starting_resolution,
    )
    return _build_result(
        counts,
        resolution=resolution,
        derived_resolution=derived_resolution,
        requested_resolution=params.resolution,
        bbox_extent_km=bbox_extent_km,
        coarsened=coarsened,
    )
