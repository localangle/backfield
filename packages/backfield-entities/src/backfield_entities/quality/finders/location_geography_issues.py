"""Find location canonicals with missing geometry or far-flung linked places."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject, StylebookLocationCanonical, SubstrateLocation
from sqlalchemy import String, and_, cast, literal, or_
from sqlmodel import Session, col, func, select

from backfield_entities.canonical.jurisdiction import (
    geojson_bbox_centroid,
    geojson_bbox_diagonal_km,
    geojson_point_lon_lat,
    haversine_km,
    point_in_geojson_bbox,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.quality.types import CleanupLocationGeographyIssueRow

LocationGeographyIssueKind = Literal["missing_geometry", "distant_linked_places"]

# Flag linked places clearly far from their catalog geography (e.g. wrong state).
DEFAULT_MIN_DISTANCE_KM: float = 150.0
_DIAGONAL_SLACK_FACTOR: float = 1.5


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


def _missing_geometry_rows(
    session: Session, *, stylebook_id: int
) -> list[CleanupLocationGeographyIssueRow]:
    rows = session.exec(
        select(StylebookLocationCanonical)
        .where(_missing_geometry_where(session, stylebook_id))
        .order_by(func.lower(StylebookLocationCanonical.label).asc())
    ).all()
    out: list[CleanupLocationGeographyIssueRow] = []
    for row in rows:
        if row.id is None:
            continue
        out.append(
            CleanupLocationGeographyIssueRow(
                id=str(row.id),
                slug=str(row.slug),
                label=str(row.label),
                location_type=str(row.location_type) if row.location_type else None,
                status=str(row.status),
                issue="missing_geometry",
            )
        )
    return out


def _distant_linked_counts_by_canonical(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
) -> dict[str, int]:
    org_project_ids = project_ids if project_ids is not None else _organization_project_ids(
        session, organization_id=organization_id
    )
    if not org_project_ids:
        return {}

    canon_rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            col(StylebookLocationCanonical.geometry_json).is_not(None),
        )
    ).all()
    canon_by_id: dict[str, StylebookLocationCanonical] = {}
    for canon in canon_rows:
        if canon.id is None:
            continue
        if not _has_geometry_json(canon.geometry_json):
            continue
        canon_by_id[str(canon.id)] = canon
    if not canon_by_id:
        return {}

    linked = session.exec(
        select(SubstrateLocation).where(
            col(SubstrateLocation.project_id).in_(org_project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(list(canon_by_id)),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_LINKED,
        )
    ).all()

    distant_counts: dict[str, int] = {}
    for substrate in linked:
        cid = substrate.stylebook_location_canonical_id
        if cid is None or cid not in canon_by_id:
            continue
        sub_gj = substrate.geometry_json
        if not isinstance(sub_gj, dict) or not _has_geometry_json(sub_gj):
            continue
        canon = canon_by_id[cid]
        canon_gj = canon.geometry_json
        if not isinstance(canon_gj, dict):
            continue
        if substrate_is_distant_from_canonical(
            substrate_geometry_json=sub_gj,
            canonical_geometry_json=canon_gj,
        ):
            distant_counts[cid] = distant_counts.get(cid, 0) + 1
    return distant_counts


def _distant_linked_rows(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
) -> list[CleanupLocationGeographyIssueRow]:
    distant_counts = _distant_linked_counts_by_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        project_ids=project_ids,
    )
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


def list_location_geography_issues(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
    limit: int,
    offset: int,
) -> tuple[list[CleanupLocationGeographyIssueRow], int]:
    missing = _missing_geometry_rows(session, stylebook_id=stylebook_id)
    distant = _distant_linked_rows(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        project_ids=project_ids,
    )
    combined = [*missing, *distant]
    combined.sort(key=lambda item: (item.label.lower(), item.issue))
    total = len(combined)
    page = combined[offset : offset + limit]
    return page, total


def count_location_geography_issues(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    project_ids: list[int] | None = None,
) -> int:
    missing_count = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookLocationCanonical)
            .where(_missing_geometry_where(session, stylebook_id))
        )
        or 0
    )
    distant_counts = _distant_linked_counts_by_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        project_ids=project_ids,
    )
    return missing_count + len(distant_counts)
