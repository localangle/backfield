"""Rebind PostGIS ``geometry`` from stored GeoJSON for half-updated location rows.

Editorial MultiPolygon / LineString writes used to clear PostGIS while leaving
``geometry_json`` and H3 intact (``str.title()`` mangled camelCase GeoJSON types).
Article geo-search keys off PostGIS, so those mentions matched nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backfield_db import StylebookLocationCanonical, SubstrateLocation
from backfield_entities.geo.geometry_bind import (
    GeometryBindError,
    assign_geojson_geometry,
    geojson_to_wkt,
)
from sqlalchemy import ColumnElement
from sqlmodel import Session, col, select


@dataclass(frozen=True)
class GeometryRebindSkip:
    table: str
    id: str
    reason: str


@dataclass(frozen=True)
class GeometryRebindResult:
    inspected_count: int
    rebound_count: int
    skipped: tuple[GeometryRebindSkip, ...]
    substrate_ids: tuple[int, ...]
    canonical_ids: tuple[str, ...]


def _geometry_is_missing(row: StylebookLocationCanonical | SubstrateLocation) -> bool:
    return row.geometry is None


def _needs_postgis_rebind(row: StylebookLocationCanonical | SubstrateLocation) -> bool:
    """True when GeoJSON is present and convertible but PostGIS is missing."""
    gj = row.geometry_json
    if not isinstance(gj, dict):
        return False
    if not _geometry_is_missing(row):
        return False
    return geojson_to_wkt(gj) is not None


def rebind_missing_location_postgis_geometry(
    session: Session,
    *,
    stylebook_id: int | None = None,
    project_id: int | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> GeometryRebindResult:
    """Recompute PostGIS from ``geometry_json`` where geo-search would otherwise miss.

    Scans canonical catalog rows and linked saved places. Does not invent geometry:
    only rows with convertible GeoJSON and a null PostGIS column are rebound.
    """
    skipped: list[GeometryRebindSkip] = []
    substrate_ids: list[int] = []
    canonical_ids: list[str] = []
    inspected = 0
    remaining = limit

    canon_filters: list[ColumnElement[bool]] = [
        col(StylebookLocationCanonical.geometry_json).is_not(None),
        col(StylebookLocationCanonical.geometry).is_(None),
    ]
    if stylebook_id is not None:
        canon_filters.append(StylebookLocationCanonical.stylebook_id == int(stylebook_id))

    canon_stmt = select(StylebookLocationCanonical).where(*canon_filters)
    if remaining is not None:
        canon_stmt = canon_stmt.limit(remaining)

    for canon in session.exec(canon_stmt).all():
        inspected += 1
        cid = str(canon.id)
        if not _needs_postgis_rebind(canon):
            skipped.append(
                GeometryRebindSkip(
                    table="stylebook_location_canonical",
                    id=cid,
                    reason="geometry_json_not_convertible",
                )
            )
            continue
        if not dry_run:
            try:
                assign_geojson_geometry(
                    session,
                    canon,
                    dict(canon.geometry_json) if isinstance(canon.geometry_json, dict) else None,
                )
            except GeometryBindError as exc:
                skipped.append(
                    GeometryRebindSkip(
                        table="stylebook_location_canonical",
                        id=cid,
                        reason=str(exc),
                    )
                )
                continue
            canon.updated_at = datetime.now(UTC)
            session.add(canon)
        canonical_ids.append(cid)
        if remaining is not None:
            remaining -= 1
            if remaining <= 0:
                return GeometryRebindResult(
                    inspected_count=inspected,
                    rebound_count=len(substrate_ids) + len(canonical_ids),
                    skipped=tuple(skipped),
                    substrate_ids=tuple(substrate_ids),
                    canonical_ids=tuple(canonical_ids),
                )

    substrate_filters: list[ColumnElement[bool]] = [
        col(SubstrateLocation.geometry_json).is_not(None),
        col(SubstrateLocation.geometry).is_(None),
    ]
    if project_id is not None:
        substrate_filters.append(SubstrateLocation.project_id == int(project_id))
    if stylebook_id is not None:
        # Limit to saved places linked into the given Stylebook catalog.
        linked_ids = select(StylebookLocationCanonical.id).where(
            StylebookLocationCanonical.stylebook_id == int(stylebook_id)
        )
        substrate_filters.append(
            col(SubstrateLocation.stylebook_location_canonical_id).in_(linked_ids)
        )

    substrate_stmt = select(SubstrateLocation).where(*substrate_filters)
    if remaining is not None:
        substrate_stmt = substrate_stmt.limit(remaining)

    for loc in session.exec(substrate_stmt).all():
        inspected += 1
        if loc.id is None:
            continue
        sid = int(loc.id)
        if not _needs_postgis_rebind(loc):
            skipped.append(
                GeometryRebindSkip(
                    table="substrate_location",
                    id=str(sid),
                    reason="geometry_json_not_convertible",
                )
            )
            continue
        if not dry_run:
            try:
                assign_geojson_geometry(
                    session,
                    loc,
                    dict(loc.geometry_json) if isinstance(loc.geometry_json, dict) else None,
                )
            except GeometryBindError as exc:
                skipped.append(
                    GeometryRebindSkip(
                        table="substrate_location",
                        id=str(sid),
                        reason=str(exc),
                    )
                )
                continue
            loc.updated_at = datetime.now(UTC)
            session.add(loc)
        substrate_ids.append(sid)

    return GeometryRebindResult(
        inspected_count=inspected,
        rebound_count=len(substrate_ids) + len(canonical_ids),
        skipped=tuple(skipped),
        substrate_ids=tuple(substrate_ids),
        canonical_ids=tuple(canonical_ids),
    )
