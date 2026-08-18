"""Apply Stylebook catalog geometry onto linked saved-place (substrate) rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backfield_db import (
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
    SubstrateLocationCache,
)
from sqlalchemy import delete
from sqlmodel import Session, col, select

from backfield_entities.canonical.link_matrix import types_are_comparable
from backfield_entities.entities.location.types import is_address_like_location_type
from backfield_entities.geo.geometry_bind import assign_geojson_geometry
from backfield_entities.ingest.geocode_cache.fingerprint import normalize_substrate_cache_query

GEOMETRY_EDITORIAL_OVERRIDE_KEY = "geometry_editorial_override"

SKIP_NOT_FOUND = "not_found"
SKIP_NOT_VISIBLE = "not_visible"
SKIP_NOT_LINKED = "not_linked"


@dataclass(frozen=True)
class GeometryApplySkip:
    id: int
    reason: str


@dataclass(frozen=True)
class GeometryApplyResult:
    updated_ids: tuple[int, ...]
    skipped: tuple[GeometryApplySkip, ...]
    cache_rows_purged: int


def suggest_substrate_for_geometry_apply(
    *,
    substrate_location_type: str | None,
    canonical_location_type: str | None,
) -> bool:
    """True when a linked saved place should be pre-checked for catalog geography apply."""
    if is_address_like_location_type(substrate_location_type):
        return False
    return types_are_comparable(substrate_location_type, canonical_location_type)


def substrate_has_editorial_geometry_override(location: SubstrateLocation) -> bool:
    """True when an editor applied catalog geography onto this saved place."""
    details = location.source_details_json if isinstance(location.source_details_json, dict) else {}
    return details.get(GEOMETRY_EDITORIAL_OVERRIDE_KEY) is True


def mark_geometry_editorial_override(location: SubstrateLocation) -> None:
    details = (
        dict(location.source_details_json)
        if isinstance(location.source_details_json, dict)
        else {}
    )
    details[GEOMETRY_EDITORIAL_OVERRIDE_KEY] = True
    location.source_details_json = details


def clear_geometry_editorial_override(location: SubstrateLocation) -> None:
    details = (
        location.source_details_json
        if isinstance(location.source_details_json, dict)
        else None
    )
    if not isinstance(details, dict) or GEOMETRY_EDITORIAL_OVERRIDE_KEY not in details:
        return
    updated = dict(details)
    updated.pop(GEOMETRY_EDITORIAL_OVERRIDE_KEY, None)
    location.source_details_json = updated or None


def apply_canonical_geometry_to_substrates(
    session: Session,
    *,
    canon: StylebookLocationCanonical,
    substrate_ids: list[int],
    visible_project_ids: list[int],
) -> GeometryApplyResult:
    """Copy catalog geometry onto selected linked saved places and purge matching cache rows."""
    requested = list(dict.fromkeys(int(sid) for sid in substrate_ids))
    visible = {int(pid) for pid in visible_project_ids}
    canonical_id = str(canon.id)
    now = datetime.now(UTC)

    skipped: list[GeometryApplySkip] = []
    updated: list[SubstrateLocation] = []

    for sid in requested:
        loc = session.get(SubstrateLocation, sid)
        if loc is None or loc.id is None:
            skipped.append(GeometryApplySkip(id=sid, reason=SKIP_NOT_FOUND))
            continue
        if int(loc.project_id) not in visible:
            skipped.append(GeometryApplySkip(id=sid, reason=SKIP_NOT_VISIBLE))
            continue
        if str(loc.stylebook_location_canonical_id or "") != canonical_id:
            skipped.append(GeometryApplySkip(id=sid, reason=SKIP_NOT_LINKED))
            continue
        gj = dict(canon.geometry_json) if isinstance(canon.geometry_json, dict) else None
        assign_geojson_geometry(session, loc, gj)
        mark_geometry_editorial_override(loc)
        loc.updated_at = now
        session.add(loc)
        updated.append(loc)

    cache_rows_purged = 0
    if updated:
        cache_rows_purged = _purge_matching_location_cache_rows(
            session,
            canon=canon,
            updated=updated,
        )

    return GeometryApplyResult(
        updated_ids=tuple(int(loc.id) for loc in updated if loc.id is not None),
        skipped=tuple(skipped),
        cache_rows_purged=cache_rows_purged,
    )


def _purge_matching_location_cache_rows(
    session: Session,
    *,
    canon: StylebookLocationCanonical,
    updated: list[SubstrateLocation],
) -> int:
    project_ids = sorted({int(loc.project_id) for loc in updated})
    keys: set[str] = set()
    label_key = normalize_substrate_cache_query(str(canon.label or ""))
    if label_key:
        keys.add(label_key)
    alias_rows = session.exec(
        select(StylebookLocationAlias.normalized_alias).where(
            StylebookLocationAlias.location_canonical_id == str(canon.id),
            StylebookLocationAlias.suppressed.is_(False),
        )
    ).all()
    for alias in alias_rows:
        key = str(alias or "").strip()
        if key:
            keys.add(key)
    for loc in updated:
        for raw in (loc.name, loc.normalized_name):
            key = normalize_substrate_cache_query(str(raw or ""))
            if key:
                keys.add(key)
    if not project_ids or not keys:
        return 0
    cache_ids = [
        int(row)
        for row in session.exec(
            select(SubstrateLocationCache.id).where(
                col(SubstrateLocationCache.project_id).in_(project_ids),
                col(SubstrateLocationCache.normalized_query).in_(sorted(keys)),
            )
        ).all()
        if row is not None
    ]
    if not cache_ids:
        return 0
    session.exec(
        delete(SubstrateLocationCache).where(col(SubstrateLocationCache.id).in_(cache_ids))
    )
    return len(cache_ids)
