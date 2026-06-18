"""Find location canonicals with missing geometry or far-flung linked places."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backfield_db import BackfieldProject, StylebookLocationCanonical, SubstrateLocation
from sqlalchemy import String, and_, cast, literal, or_, text
from sqlmodel import Session, col, func, select

from backfield_entities.canonical.jurisdiction import (
    geojson_bbox_centroid,
    geojson_bbox_diagonal_km,
    geojson_point_lon_lat,
    haversine_km,
    point_in_geojson_bbox,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.quality.dismissals import load_dismissed_keys
from backfield_entities.quality.types import CleanupLocationGeographyIssueRow

_GEOGRAPHY_CHECK_ID = "missing-geometry-locations"

LocationGeographyIssueKind = Literal["missing_geometry", "distant_linked_places"]

# Flag linked places clearly far from their catalog geography (e.g. wrong state).
DEFAULT_MIN_DISTANCE_KM: float = 150.0
DEFAULT_MIN_DISTANCE_M: float = DEFAULT_MIN_DISTANCE_KM * 1000.0
_DIAGONAL_SLACK_FACTOR: float = 1.5


@dataclass(frozen=True)
class _CanonicalGeoCache:
    geometry_json: dict
    centroid: tuple[float, float]
    threshold_km: float


def _missing_geometry_json_filter():
    geometry_json_col = col(StylebookLocationCanonical.geometry_json)
    return or_(
        geometry_json_col.is_(None),
        cast(geometry_json_col, String) == literal("null"),
    )


def _missing_geometry_where(session: Session, stylebook_id: int):
    filters: list = [
        StylebookLocationCanonical.stylebook_id == stylebook_id,
        _missing_geometry_json_filter(),
    ]
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        filters.append(col(StylebookLocationCanonical.geometry).is_(None))
    return and_(*filters)


def _has_geometry_json(geometry_json: object | None) -> bool:
    if not isinstance(geometry_json, dict):
        return False
    coords = geometry_json.get("coordinates")
    if coords is None:
        return False
    if isinstance(coords, (list, tuple)) and len(coords) == 0:
        return False
    return True


def _substrate_lon_lat(geometry_json: dict) -> tuple[float, float] | None:
    return geojson_point_lon_lat(geometry_json) or geojson_bbox_centroid(geometry_json)


def _distance_threshold_km(canonical_geometry_json: dict) -> float:
    diagonal = geojson_bbox_diagonal_km(canonical_geometry_json)
    if diagonal is None or diagonal <= 0:
        return DEFAULT_MIN_DISTANCE_KM
    return max(DEFAULT_MIN_DISTANCE_KM, diagonal * _DIAGONAL_SLACK_FACTOR)


def substrate_is_distant_from_canonical(
    *,
    substrate_geometry_json: dict,
    canonical_geometry_json: dict,
    min_distance_km: float = DEFAULT_MIN_DISTANCE_KM,
) -> bool:
    """True when substrate geometry is clearly outside the canonical's geography."""
    sub_ll = _substrate_lon_lat(substrate_geometry_json)
    if sub_ll is None:
        return False
    lon, lat = sub_ll
    if point_in_geojson_bbox(lon, lat, canonical_geometry_json):
        return False
    canon_centroid = geojson_bbox_centroid(canonical_geometry_json) or geojson_point_lon_lat(
        canonical_geometry_json
    )
    if canon_centroid is None:
        return False
    threshold = max(min_distance_km, _distance_threshold_km(canonical_geometry_json))
    dist_km = haversine_km(lon, lat, canon_centroid[0], canon_centroid[1])
    return dist_km > threshold


def _organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _row_from_missing_canonical(
    row: StylebookLocationCanonical,
) -> CleanupLocationGeographyIssueRow:
    return CleanupLocationGeographyIssueRow(
        id=str(row.id),
        slug=str(row.slug),
        label=str(row.label),
        location_type=str(row.location_type) if row.location_type else None,
        status=str(row.status),
        issue="missing_geometry",
    )


def _count_missing_geometry(
    session: Session,
    *,
    stylebook_id: int,
    exclude_ids: set[str] | None = None,
) -> int:
    filters = [_missing_geometry_where(session, stylebook_id)]
    if exclude_ids:
        filters.append(col(StylebookLocationCanonical.id).notin_(exclude_ids))
    return int(
        session.scalar(
            select(func.count())
            .select_from(StylebookLocationCanonical)
            .where(*filters)
        )
        or 0
    )


def _list_missing_geometry_page(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    exclude_ids: set[str] | None = None,
) -> list[CleanupLocationGeographyIssueRow]:
    filters = [_missing_geometry_where(session, stylebook_id)]
    if exclude_ids:
        filters.append(col(StylebookLocationCanonical.id).notin_(exclude_ids))
    rows = session.exec(
        select(StylebookLocationCanonical)
        .where(*filters)
        .order_by(func.lower(StylebookLocationCanonical.label).asc())
        .offset(offset)
        .limit(limit)
    ).all()
    out: list[CleanupLocationGeographyIssueRow] = []
    for row in rows:
        if row.id is None:
            continue
        out.append(_row_from_missing_canonical(row))
    return out


def _canonical_geo_cache(geometry_json: dict) -> _CanonicalGeoCache | None:
    centroid = geojson_bbox_centroid(geometry_json) or geojson_point_lon_lat(geometry_json)
    if centroid is None:
        return None
    return _CanonicalGeoCache(
        geometry_json=geometry_json,
        centroid=centroid,
        threshold_km=_distance_threshold_km(geometry_json),
    )


def _distant_linked_counts_sqlite(
    session: Session,
    *,
    stylebook_id: int,
    project_ids: list[int],
) -> dict[str, int]:
    if not project_ids:
        return {}

    canon_rows = session.exec(
        select(
            StylebookLocationCanonical.id,
            StylebookLocationCanonical.geometry_json,
        ).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            col(StylebookLocationCanonical.geometry_json).is_not(None),
        )
    ).all()
    geo_by_id: dict[str, _CanonicalGeoCache] = {}
    for row_id, geometry_json in canon_rows:
        if row_id is None or not _has_geometry_json(geometry_json):
            continue
        assert isinstance(geometry_json, dict)
        cached = _canonical_geo_cache(geometry_json)
        if cached is not None:
            geo_by_id[str(row_id)] = cached
    if not geo_by_id:
        return {}

    linked = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            SubstrateLocation.geometry_json,
        ).where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(list(geo_by_id)),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstrateLocation.geometry_json).is_not(None),
        )
    ).all()

    distant_counts: dict[str, int] = {}
    for canonical_id, sub_gj in linked:
        if canonical_id is None or canonical_id not in geo_by_id:
            continue
        if not isinstance(sub_gj, dict) or not _has_geometry_json(sub_gj):
            continue
        cache = geo_by_id[canonical_id]
        sub_ll = _substrate_lon_lat(sub_gj)
        if sub_ll is None:
            continue
        lon, lat = sub_ll
        if point_in_geojson_bbox(lon, lat, cache.geometry_json):
            continue
        dist_km = haversine_km(lon, lat, cache.centroid[0], cache.centroid[1])
        if dist_km > cache.threshold_km:
            distant_counts[canonical_id] = distant_counts.get(canonical_id, 0) + 1
    return distant_counts


def _distant_linked_rows_for_ids(
    session: Session,
    distant_counts: dict[str, int],
) -> list[CleanupLocationGeographyIssueRow]:
    if not distant_counts:
        return []
    canon_rows = session.exec(
        select(StylebookLocationCanonical).where(
            col(StylebookLocationCanonical.id).in_(list(distant_counts))
        )
    ).all()
    out: list[CleanupLocationGeographyIssueRow] = []
    for row in canon_rows:
        if row.id is None:
            continue
        cid = str(row.id)
        count = distant_counts.get(cid, 0)
        if count <= 0:
            continue
        out.append(
            CleanupLocationGeographyIssueRow(
                id=cid,
                slug=str(row.slug),
                label=str(row.label),
                location_type=str(row.location_type) if row.location_type else None,
                status=str(row.status),
                issue="distant_linked_places",
                distant_linked_count=count,
            )
        )
    out.sort(key=lambda item: item.label.lower())
    return out


def _postgres_project_filter(project_ids: list[int]) -> tuple[str, dict[str, object]]:
    if not project_ids:
        return "FALSE", {}
    return "s.project_id = ANY(:project_ids)", {"project_ids": project_ids}


_EMPTY_DISTANT_CTE = """
        distant AS (
            SELECT
                NULL::text AS id,
                NULL::text AS slug,
                NULL::text AS label,
                NULL::text AS location_type,
                NULL::text AS status,
                NULL::text AS issue,
                0::int AS distant_linked_count
            WHERE FALSE
        )
    """

_DISTANT_UNION = """
            UNION ALL
            SELECT id, slug, label, location_type, status, issue, distant_linked_count
            FROM distant
        """


def _count_distant_linked_postgres(
    session: Session,
    *,
    stylebook_id: int,
    project_ids: list[int],
    exclude_ids: set[str] | None = None,
) -> int:
    if not project_ids:
        return 0
    project_filter, bind = _postgres_project_filter(project_ids)
    exclude_filter = ""
    if exclude_ids:
        exclude_filter = "AND c.id::text <> ALL(:exclude_ids)"
    stmt = text(
        f"""
        SELECT COUNT(DISTINCT c.id)
        FROM stylebook_location_canonical AS c
        INNER JOIN substrate_location AS s
            ON s.stylebook_location_canonical_id = c.id
        WHERE c.stylebook_id = :stylebook_id
          AND {project_filter}
          AND s.canonical_link_status = :linked_status
          AND c.geometry IS NOT NULL
          AND s.geometry IS NOT NULL
          AND NOT ST_Covers(c.geometry, s.geometry)
          AND ST_DistanceSphere(
                ST_Centroid(s.geometry),
                ST_Centroid(c.geometry)
              ) > :min_distance_m
          {exclude_filter}
        """
    )
    params: dict[str, object] = {
        "stylebook_id": stylebook_id,
        "linked_status": CANONICAL_LINK_LINKED,
        "min_distance_m": DEFAULT_MIN_DISTANCE_M,
        **bind,
    }
    if exclude_ids:
        params["exclude_ids"] = list(exclude_ids)
    return int(session.scalar(stmt, params) or 0)


def _list_location_geography_issues_postgres(
    session: Session,
    *,
    stylebook_id: int,
    project_ids: list[int],
    limit: int,
    offset: int,
    exclude_ids: set[str] | None = None,
) -> tuple[list[CleanupLocationGeographyIssueRow], int]:
    missing_total = _count_missing_geometry(
        session,
        stylebook_id=stylebook_id,
        exclude_ids=exclude_ids,
    )
    distant_total = _count_distant_linked_postgres(
        session,
        stylebook_id=stylebook_id,
        project_ids=project_ids,
        exclude_ids=exclude_ids,
    )
    total = missing_total + distant_total
    if total == 0 or offset >= total:
        return [], total

    project_filter, bind = _postgres_project_filter(project_ids)
    exclude_filter = ""
    if exclude_ids:
        exclude_filter = "AND id::text <> ALL(:exclude_ids)"
    distant_exclude_filter = ""
    if exclude_ids:
        distant_exclude_filter = "AND c.id::text <> ALL(:exclude_ids)"
    distant_cte = f"""
        distant AS (
            SELECT
                c.id::text AS id,
                c.slug AS slug,
                c.label AS label,
                c.location_type AS location_type,
                c.status AS status,
                'distant_linked_places'::text AS issue,
                COUNT(s.id)::int AS distant_linked_count
            FROM stylebook_location_canonical AS c
            INNER JOIN substrate_location AS s
                ON s.stylebook_location_canonical_id = c.id
            WHERE c.stylebook_id = :stylebook_id
              AND {project_filter}
              AND s.canonical_link_status = :linked_status
              AND c.geometry IS NOT NULL
              AND s.geometry IS NOT NULL
              AND NOT ST_Covers(c.geometry, s.geometry)
              AND ST_DistanceSphere(
                    ST_Centroid(s.geometry),
                    ST_Centroid(c.geometry)
                  ) > :min_distance_m
              {distant_exclude_filter}
            GROUP BY c.id, c.slug, c.label, c.location_type, c.status
        )
    """
    distant_union = _DISTANT_UNION if project_ids else ""
    distant_cte_sql = distant_cte if project_ids else _EMPTY_DISTANT_CTE

    stmt = text(
        f"""
        WITH missing AS (
            SELECT
                id::text AS id,
                slug AS slug,
                label AS label,
                location_type AS location_type,
                status AS status,
                'missing_geometry'::text AS issue,
                0::int AS distant_linked_count
            FROM stylebook_location_canonical
            WHERE stylebook_id = :stylebook_id
              AND (
                    geometry_json IS NULL
                 OR geometry_json::text = 'null'
              )
              AND geometry IS NULL
              {exclude_filter}
        ),
        {distant_cte_sql}
        SELECT id, slug, label, location_type, status, issue, distant_linked_count
        FROM (
            SELECT id, slug, label, location_type, status, issue, distant_linked_count
            FROM missing
            {distant_union}
        ) AS combined
        WHERE id IS NOT NULL
        ORDER BY lower(label) ASC, issue ASC
        LIMIT :limit OFFSET :offset
        """
    )
    params: dict[str, object] = {
        "stylebook_id": stylebook_id,
        "linked_status": CANONICAL_LINK_LINKED,
        "min_distance_m": DEFAULT_MIN_DISTANCE_M,
        "limit": limit,
        "offset": offset,
        **bind,
    }
    if exclude_ids:
        params["exclude_ids"] = list(exclude_ids)
    rows = session.execute(stmt, params).all()
    items = [
        CleanupLocationGeographyIssueRow(
            id=str(row.id),
            slug=str(row.slug),
            label=str(row.label),
            location_type=str(row.location_type) if row.location_type else None,
            status=str(row.status),
            issue=(
                "distant_linked_places"
                if row.issue == "distant_linked_places"
                else "missing_geometry"
            ),
            distant_linked_count=int(row.distant_linked_count or 0),
        )
        for row in rows
    ]
    return items, total


def _list_location_geography_issues_sqlite(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None,
    limit: int,
    offset: int,
    exclude_ids: set[str] | None = None,
) -> tuple[list[CleanupLocationGeographyIssueRow], int]:
    org_project_ids = project_ids if project_ids is not None else _organization_project_ids(
        session, organization_id=organization_id
    )
    missing_total = _count_missing_geometry(
        session,
        stylebook_id=stylebook_id,
        exclude_ids=exclude_ids,
    )
    distant_counts = _distant_linked_counts_sqlite(
        session,
        stylebook_id=stylebook_id,
        project_ids=org_project_ids,
    )
    if exclude_ids:
        for canonical_id in exclude_ids:
            distant_counts.pop(canonical_id, None)
    distant_rows = _distant_linked_rows_for_ids(session, distant_counts)
    total = missing_total + len(distant_rows)
    if total == 0 or offset >= total:
        return [], total

    page: list[CleanupLocationGeographyIssueRow] = []
    if offset < missing_total:
        missing_limit = min(limit, missing_total - offset)
        page.extend(
            _list_missing_geometry_page(
                session,
                stylebook_id=stylebook_id,
                limit=missing_limit,
                offset=offset,
                exclude_ids=exclude_ids,
            )
        )
        remaining = limit - len(page)
        if remaining > 0:
            page.extend(distant_rows[:remaining])
    else:
        distant_offset = offset - missing_total
        page.extend(distant_rows[distant_offset : distant_offset + limit])
    return page, total


def list_location_geography_issues(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
    limit: int,
    offset: int,
) -> tuple[list[CleanupLocationGeographyIssueRow], int]:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=_GEOGRAPHY_CHECK_ID,
    )
    exclude_ids = dismissed or None
    bind = session.get_bind()
    org_project_ids = project_ids if project_ids is not None else _organization_project_ids(
        session, organization_id=organization_id
    )
    if bind is not None and bind.dialect.name == "postgresql":
        return _list_location_geography_issues_postgres(
            session,
            stylebook_id=stylebook_id,
            project_ids=org_project_ids,
            limit=limit,
            offset=offset,
            exclude_ids=exclude_ids,
        )
    return _list_location_geography_issues_sqlite(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        project_ids=project_ids,
        limit=limit,
        offset=offset,
        exclude_ids=exclude_ids,
    )


def count_location_geography_issues(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
) -> int:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=_GEOGRAPHY_CHECK_ID,
    )
    exclude_ids = dismissed or None
    missing_count = _count_missing_geometry(
        session,
        stylebook_id=stylebook_id,
        exclude_ids=exclude_ids,
    )
    org_project_ids = project_ids if project_ids is not None else _organization_project_ids(
        session, organization_id=organization_id
    )
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        distant_count = _count_distant_linked_postgres(
            session,
            stylebook_id=stylebook_id,
            project_ids=org_project_ids,
            exclude_ids=exclude_ids,
        )
    else:
        distant_counts = _distant_linked_counts_sqlite(
            session,
            stylebook_id=stylebook_id,
            project_ids=org_project_ids,
        )
        if exclude_ids:
            for canonical_id in exclude_ids:
                distant_counts.pop(canonical_id, None)
        distant_count = len(distant_counts)
    return missing_count + distant_count
