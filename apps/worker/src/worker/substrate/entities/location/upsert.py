"""Location geometry, cache rows, and durable location upserts for substrate persistence."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backfield_db import SubstrateLocation, SubstrateLocationCache
from backfield_entities.entities.location.geometry_apply import (
    clear_geometry_editorial_override,
    substrate_has_editorial_geometry_override,
)
from backfield_entities.geo.geometry_bind import geometry_bind_value, geometry_is_geography_safe
from backfield_entities.geo.h3_index import derive_h3_index
from backfield_entities.ingest.geocode_cache.fingerprint import (
    substrate_location_cache_query_fingerprint,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from worker.substrate.common import _normalize_name, _sha256_hex, _utcnow

logger = logging.getLogger(__name__)

# Consolidated place payload key from GeocodeAgent (ignored by geometry/canonical logic).
_AGATE_GEOCODE_ROUTER_AUDIT_KEY = "agate_geocode_router_audit"

# Fine-grained POIs sharing one Stylebook canonical still get distinct substrate rows.
_FINE_GRAINED_LOCATION_TYPES_DISAMBIGUATE_BY_NAME = frozenset(
    {
        "place",
        "point",
        "address",
        "intersection_road",
        "intersection_highway",
        "street_road",
    }
)
# Admin types: Stylebook candidate IDs must not collapse distinct names
# (Bucktown vs Uptown both carrying the same poisoned canonical UUID).
_ADMIN_LOCATION_TYPES_DISAMBIGUATE_BY_NAME = frozenset(
    {
        "neighborhood",
        "city",
        "town",
        "village",
        "county",
        "community_area",
        "borough",
        "suburb",
        "district",
        "ward",
        "region_city",
        "political_district",
    }
)
_STYLEBOOK_LOCATION_TYPES_DISAMBIGUATE_BY_NAME = (
    _FINE_GRAINED_LOCATION_TYPES_DISAMBIGUATE_BY_NAME | _ADMIN_LOCATION_TYPES_DISAMBIGUATE_BY_NAME
)


@dataclass(frozen=True)
class LocationUpsertResult:
    location: SubstrateLocation
    created: bool
    updated: bool


def _router_audit_from_place_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    raw = entry.get(_AGATE_GEOCODE_ROUTER_AUDIT_KEY)
    return raw if isinstance(raw, dict) else None


def _place_extract_persist_fields_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Fields from the geocode ``entry`` merged into ``SubstrateLocation.source_details_json``."""
    out: dict[str, Any] = {}
    comps = entry.get("components")
    if isinstance(comps, dict):
        out["place_extract_components"] = comps
    kind = entry.get("address_place_kind")
    if isinstance(kind, str) and kind.strip():
        out["address_place_kind"] = kind.strip().lower()
    return out


def _upsert_location_cache(
    session: Session,
    *,
    project_id: int,
    query_text: str,
    location_type: str | None,
    entry: dict[str, Any],
    geocode_type: str | None,
    geocode_result: dict[str, Any] | None,
    geometry_json: dict[str, Any] | None,
    geometry_value: object | None,
    geometry_type_str: str | None,
    formatted_address: str | None,
    h3_cell: str | None,
    h3_resolution: int | None,
) -> None:
    normalized_query = _normalize_name(query_text)
    if not normalized_query:
        return

    fingerprint = substrate_location_cache_query_fingerprint(
        project_id=project_id,
        normalized_query=normalized_query,
        location_type=location_type,
    )

    external_source, external_id = (
        _external_identity_from_geocode_result(
            geocode_result,
            display_name=query_text,
            location_type=location_type,
        )
        if geocode_result
        else (None, None)
    )

    now = _utcnow()
    payload = {
        "places_entry": entry,
        "geocode_result": geocode_result,
    }
    candidate = SubstrateLocationCache(
        project_id=project_id,
        query_text=query_text,
        normalized_query=normalized_query,
        query_fingerprint=fingerprint,
        request_components_json=None,
        external_source=external_source,
        external_id=external_id,
        location_name=query_text,
        location_type=location_type,
        geocode_type=geocode_type,
        formatted_address=formatted_address,
        geometry=geometry_value,
        geometry_type=geometry_type_str,
        geometry_json=geometry_json,
        h3_cell=h3_cell,
        h3_resolution=h3_resolution,
        response_payload_json=payload,
    )

    row = _select_location_cache_row_for_update(
        session, project_id=project_id, query_fingerprint=fingerprint
    )
    if row is None:
        # ``FOR UPDATE`` on a missing row locks nothing, so another item may insert the same
        # query between the select above and this insert. Insert inside a savepoint and fall
        # back to updating the winner's row instead of failing the whole persist.
        try:
            with session.begin_nested():
                session.add(candidate)
        except IntegrityError:
            row = _select_location_cache_row_for_update(
                session, project_id=project_id, query_fingerprint=fingerprint
            )
            if row is None:
                raise
    if row is not None:
        _merge_location_cache_row(row, candidate, now=now)
        session.add(row)

    session.flush()


def _select_location_cache_row_for_update(
    session: Session, *, project_id: int, query_fingerprint: str
) -> SubstrateLocationCache | None:
    return session.exec(
        select(SubstrateLocationCache)
        .where(
            col(SubstrateLocationCache.project_id) == project_id,
            col(SubstrateLocationCache.query_fingerprint) == query_fingerprint,
        )
        .with_for_update()
    ).first()


def _merge_location_cache_row(
    row: SubstrateLocationCache, candidate: SubstrateLocationCache, *, now: datetime
) -> None:
    """Update an existing cache row with a newer lookup; empty new values keep the old ones."""
    row.query_text = candidate.query_text
    row.normalized_query = candidate.normalized_query
    row.external_source = candidate.external_source or row.external_source
    row.external_id = candidate.external_id or row.external_id
    row.location_name = candidate.location_name
    row.location_type = candidate.location_type or row.location_type
    row.geocode_type = candidate.geocode_type or row.geocode_type
    row.formatted_address = candidate.formatted_address or row.formatted_address
    row.geometry = candidate.geometry or row.geometry
    row.geometry_type = candidate.geometry_type or row.geometry_type
    row.geometry_json = candidate.geometry_json or row.geometry_json
    row.h3_cell = candidate.h3_cell or row.h3_cell
    row.h3_resolution = (
        candidate.h3_resolution if candidate.h3_resolution is not None else row.h3_resolution
    )
    row.response_payload_json = candidate.response_payload_json
    row.updated_at = now


def _delete_location_cache(
    session: Session,
    *,
    project_id: int,
    query_text: str,
    location_type: str | None,
) -> None:
    """Remove a previously accepted cache row after a review/rejection outcome."""
    normalized_query = _normalize_name(query_text)
    if not normalized_query:
        return
    fingerprint = substrate_location_cache_query_fingerprint(
        project_id=project_id,
        normalized_query=normalized_query,
        location_type=location_type,
    )
    row = session.exec(
        select(SubstrateLocationCache).where(
            col(SubstrateLocationCache.project_id) == project_id,
            col(SubstrateLocationCache.query_fingerprint) == fingerprint,
        )
    ).first()
    if row is not None:
        session.delete(row)
        session.flush()


def _stylebook_prefixed_external_id(value: str) -> str:
    """Return ``stylebook:{canonical_uuid}`` for substrate ``external_id`` (no name suffix)."""
    s = _stylebook_canonical_uuid_only(str(value).strip())
    if not s:
        return ""
    return f"stylebook:{s}"


def _stylebook_canonical_uuid_only(canonical_or_prefixed: str) -> str:
    """Strip ``stylebook:`` and any prior POI name suffix from a canonical key."""
    s = str(canonical_or_prefixed).strip()
    if not s:
        return s
    if s.lower().startswith("stylebook:"):
        s = s.split(":", 1)[1].strip()
    if ":" in s:
        uuid_part, _suffix = s.split(":", 1)
        return uuid_part.strip() or s
    return s


def _stylebook_identity_disambiguates_by_name(location_type: str | None) -> bool:
    if not location_type:
        return False
    return location_type.lower() in _STYLEBOOK_LOCATION_TYPES_DISAMBIGUATE_BY_NAME


def _geocoder_identity_disambiguates_by_name(location_type: str | None) -> bool:
    """Geocoder provider ids only need POI-level disambiguation, not admin types."""
    if not location_type:
        return False
    return location_type.lower() in _FINE_GRAINED_LOCATION_TYPES_DISAMBIGUATE_BY_NAME


def _stylebook_place_name_identity_suffix(display_name: str) -> str:
    normalized = _normalize_name(display_name)
    if not normalized:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not slug:
        slug = _sha256_hex(normalized)[:16]
    return slug[:64]


def _stylebook_location_external_id(
    canonical_key: str,
    *,
    display_name: str,
    location_type: str | None,
) -> str:
    base = _stylebook_prefixed_external_id(canonical_key)
    if not base:
        return base
    if not _stylebook_identity_disambiguates_by_name(location_type):
        return base
    suffix = _stylebook_place_name_identity_suffix(display_name)
    if suffix:
        return f"{base}:{suffix}"
    return base


def _geocoder_location_external_id(
    raw_id: str,
    *,
    display_name: str,
    location_type: str | None,
) -> str:
    """Disambiguate shared geocoder address/building ids for fine-grained POIs."""
    base = str(raw_id).strip()
    if not base:
        return base
    if not _geocoder_identity_disambiguates_by_name(location_type):
        return base
    suffix = _stylebook_place_name_identity_suffix(display_name)
    if suffix:
        return f"{base}:{suffix}"
    return base


def _external_identity_from_geocode_result(
    result: dict[str, Any],
    *,
    display_name: str = "",
    location_type: str | None = None,
) -> tuple[str | None, str | None]:
    canonical_id = result.get("canonical_id")
    if canonical_id is not None:
        raw = str(canonical_id).strip()
        if raw:
            return (
                "stylebook_location",
                _stylebook_location_external_id(
                    raw,
                    display_name=display_name,
                    location_type=location_type,
                ),
            )

    rid = result.get("id")
    if rid is None:
        return None, None
    rid_str = str(rid).strip()
    if rid_str.startswith("stylebook:"):
        return (
            "stylebook_location",
            _stylebook_location_external_id(
                rid_str,
                display_name=display_name,
                location_type=location_type,
            ),
        )
    if rid_str.startswith("wof:"):
        return "wof", rid_str
    if rid_str.startswith("pelias:"):
        return "pelias", rid_str
    if rid_str.startswith("geocodio:"):
        return "geocodio", rid_str
    if rid_str.startswith("h3:"):
        # H3 cells are spatial buckets, not place identity. Distinct POIs in the same
        # building can share a cell and must remain separate substrate rows.
        return None, None
    return (
        "geocoder",
        _geocoder_location_external_id(
            rid_str,
            display_name=display_name,
            location_type=location_type,
        ),
    )


def _raw_entry_id_for_source_details(entry: dict[str, Any], *, display_name: str) -> Any:
    raw = entry.get("id")
    if not isinstance(raw, str):
        return raw
    value = raw.strip()
    if value.startswith("h3:"):
        suffix = _normalize_name(display_name)
        if suffix:
            return f"{value}:{suffix}"
    return raw


def _fingerprint_for_location(
    *,
    project_id: int,
    location_type: str | None,
    external_source: str | None,
    external_id: str | None,
    geometry_json: dict[str, Any] | None,
    formatted_address: str | None,
    display_name: str,
) -> str:
    payload = {
        "project_id": project_id,
        "location_type": location_type,
        "external_source": external_source,
        "external_id": external_id,
        "geometry_json": geometry_json,
        "formatted_address": formatted_address,
        "display_name": display_name,
    }
    return _sha256_hex(json.dumps(payload, sort_keys=True, default=str))


def location_identities_for_entries(
    *, project_id: int, entries: Iterable[tuple[str, dict[str, Any]]]
) -> tuple[set[str], set[tuple[str, str]]]:
    """Identity fingerprints and (source, id) pairs that the entries' upserts will look up."""
    fingerprints: set[str] = set()
    external_identities: set[tuple[str, str]] = set()
    for bucket, entry in entries:
        fields = _location_fields_for_entry(project_id=project_id, bucket=bucket, entry=entry)
        if fields is None:
            continue
        fingerprints.add(fields.fingerprint)
        if fields.external_source and fields.external_id:
            external_identities.add((fields.external_source, fields.external_id))
    return fingerprints, external_identities


def _iter_place_entries(places: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    areas = places.get("areas") if isinstance(places.get("areas"), dict) else {}
    for bucket in ("states", "counties", "cities", "neighborhoods", "regions", "other"):
        items = areas.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                yield f"areas.{bucket}", item

    points = places.get("points")
    if isinstance(points, list):
        for item in points:
            if isinstance(item, dict):
                yield "points", item

    needs = places.get("needs_review")
    if isinstance(needs, list):
        for item in needs:
            if isinstance(item, dict):
                yield "needs_review", item


def _display_name_for_place_entry(entry: dict[str, Any]) -> str:
    loc = entry.get("location")
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    if isinstance(loc, dict):
        full = loc.get("full")
        if isinstance(full, str) and full.strip():
            return full.strip()
    formatted = entry.get("formatted_address")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    original = entry.get("original_text")
    if isinstance(original, str) and original.strip():
        return original.strip()
    return "Unknown location"


def _h3_parts_from_geometry(
    geometry_json: dict[str, Any] | None,
) -> tuple[str | None, int | None]:
    derived = derive_h3_index(geometry_json)
    if derived is None:
        return None, None
    return derived.h3_cell, derived.h3_resolution


def _raw_geometry_json_from_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    result = geocode.get("result") if geocode and isinstance(geocode.get("result"), dict) else None
    if result and isinstance(result.get("geometry"), dict):
        return dict(result["geometry"])
    if isinstance(entry.get("geometry"), dict):
        return dict(entry["geometry"])
    return None


def _geometry_json_from_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Entry geometry, or None when it cannot be stored (e.g. a world-sized bounding box)."""
    geometry_json = _raw_geometry_json_from_entry(entry)
    if geometry_json is not None and not geometry_is_geography_safe(geometry_json):
        logger.warning(
            "Dropping geometry too wide to store for place %r",
            _display_name_for_place_entry(entry),
        )
        return None
    return geometry_json


def _formatted_address_from_entry(entry: dict[str, Any]) -> str | None:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    result = geocode.get("result") if geocode and isinstance(geocode.get("result"), dict) else None
    if result:
        formatted = result.get("formatted_address") or result.get("processed_str")
        if isinstance(formatted, str) and formatted.strip():
            return formatted.strip()
    formatted = entry.get("formatted_address")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    return None


def _geocode_meta_from_entry(entry: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    if not geocode:
        return None, None
    geocode_type = geocode.get("geocode_type")
    geocode_type_str = str(geocode_type) if geocode_type is not None else None
    result = geocode.get("result") if isinstance(geocode.get("result"), dict) else None
    return geocode_type_str, result


# Shared location rows are referenced by foreign keys from mentions and semantic documents, and
# every inserted child row takes ``FOR KEY SHARE`` on its parent.
# ``with_for_update(key_share=True)`` renders ``FOR NO KEY UPDATE``: it still excludes other
# writers but does not conflict with that check, so items that only insert child rows no longer
# wait on (and deadlock with) items that are updating the location. Use it for every explicit
# lock on ``substrate_location``.


def _lock_substrate_location_row(session: Session, location_id: int) -> SubstrateLocation:
    row = session.exec(
        select(SubstrateLocation)
        .where(col(SubstrateLocation.id) == int(location_id))
        .with_for_update(key_share=True)
    ).first()
    if row is None:
        raise RuntimeError(f"substrate_location id={location_id} disappeared during upsert lock")
    return row


def _select_existing_substrate_location(
    session: Session,
    *,
    project_id: int,
    external_source: str | None,
    external_id: str | None,
    fingerprint: str,
) -> SubstrateLocation | None:
    """Load an existing durable location row with ``FOR UPDATE`` when found."""
    if external_source and external_id:
        row = session.exec(
            select(SubstrateLocation)
            .where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.external_source) == external_source,
                col(SubstrateLocation.external_id) == external_id,
            )
            .with_for_update(key_share=True)
        ).first()
        if row is not None:
            return row
    return session.exec(
        select(SubstrateLocation)
        .where(
            col(SubstrateLocation.project_id) == project_id,
            col(SubstrateLocation.identity_fingerprint) == fingerprint,
        )
        .with_for_update(key_share=True)
    ).first()


def _fetch_substrate_location_after_unique_violation(
    session: Session,
    *,
    project_id: int,
    external_source: str | None,
    external_id: str | None,
    identity_fingerprint: str,
) -> SubstrateLocation | None:
    """Re-load row after concurrent insert hit ``uq_substrate_location_*``."""
    if external_source and external_id:
        row = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.external_source) == external_source,
                col(SubstrateLocation.external_id) == external_id,
            )
        ).first()
        if row is not None:
            return row
    return session.exec(
        select(SubstrateLocation).where(
            col(SubstrateLocation.project_id) == project_id,
            col(SubstrateLocation.identity_fingerprint) == identity_fingerprint,
        )
    ).first()


def _apply_substrate_location_merge(
    loc: SubstrateLocation,
    *,
    display_name: str,
    normalized: str,
    location_type_str: str | None,
    status: str,
    external_source: str | None,
    external_id: str | None,
    fingerprint: str,
    geocode_type: str | None,
    formatted_address: str | None,
    details: dict[str, Any],
    geometry_value: object | None,
    geometry_type_str: str | None,
    geometry_json: dict[str, Any] | None,
    geocode_router_audit_json: dict[str, Any] | None,
    h3_cell: str | None,
    h3_resolution: int | None,
    clear_geocode_identity: bool = False,
) -> None:
    now = _utcnow()
    loc.name = display_name
    loc.normalized_name = normalized
    loc.location_type = location_type_str or loc.location_type
    loc.status = status
    loc.identity_fingerprint = fingerprint
    loc.source_kind = "agate_geocode"
    prev_details = loc.source_details_json if isinstance(loc.source_details_json, dict) else {}
    loc.source_details_json = {**prev_details, **details}
    keep_editorial_geometry = (
        not clear_geocode_identity and substrate_has_editorial_geometry_override(loc)
    )
    if clear_geocode_identity:
        loc.external_source = None
        loc.external_id = None
        loc.geocode_type = None
        loc.formatted_address = None
        loc.geometry = None
        loc.geometry_type = None
        loc.geometry_json = None
        loc.h3_cell = None
        loc.h3_resolution = None
        clear_geometry_editorial_override(loc)
    else:
        loc.external_source = external_source or loc.external_source
        loc.external_id = external_id or loc.external_id
        loc.geocode_type = geocode_type or loc.geocode_type
        loc.formatted_address = formatted_address or loc.formatted_address
        if not keep_editorial_geometry:
            loc.geometry = geometry_value or loc.geometry
            loc.geometry_type = geometry_type_str or loc.geometry_type
            loc.geometry_json = geometry_json or loc.geometry_json
    if geometry_json is not None and not clear_geocode_identity and not keep_editorial_geometry:
        loc.h3_cell = h3_cell
        loc.h3_resolution = h3_resolution
    # Latest ingest wins when the payload carries an audit dict (Advanced path).
    if geocode_router_audit_json is not None:
        loc.geocode_router_audit_json = geocode_router_audit_json
    loc.updated_at = now


@dataclass(frozen=True)
class _LocationEntryFields:
    """What a place entry contributes to its ``substrate_location`` row (no session needed)."""

    display_name: str
    normalized: str
    location_type_str: str | None
    geometry_json: dict[str, Any] | None
    geometry_type_str: str | None
    h3_cell: str | None
    h3_resolution: int | None
    formatted_address: str | None
    geocode_type: str | None
    geocode_result: dict[str, Any] | None
    authoritative_rejection: bool
    external_source: str | None
    external_id: str | None
    fingerprint: str


def _location_fields_for_entry(
    *, project_id: int, bucket: str, entry: dict[str, Any]
) -> _LocationEntryFields | None:
    """Derive the row identity and geocode fields for a place entry (None when it has no name).

    Pure in the entry, so the ordered row pre-lock and the upsert always agree on which
    ``substrate_location`` row an entry maps to.
    """
    display_name = _display_name_for_place_entry(entry)
    normalized = _normalize_name(display_name)
    if not normalized:
        return None

    location_type = entry.get("type")
    location_type_str = str(location_type).lower() if location_type is not None else None

    geocoded = entry.get("geocoded")
    geometry_json = _geometry_json_from_entry(entry)
    geometry_type = geometry_json.get("type") if geometry_json else None
    geometry_type_str = str(geometry_type) if geometry_type else None
    h3_cell, h3_resolution = _h3_parts_from_geometry(geometry_json)
    formatted_address = _formatted_address_from_entry(entry)
    geocode_type, geocode_result = _geocode_meta_from_entry(entry)
    disposition = str(entry.get("geocode_disposition") or "").strip().lower()
    authoritative_rejection = bucket == "needs_review" and (
        geocoded is False
        or bool(entry.get("geocode_qa_code"))
        or bool(entry.get("reason"))
        or disposition in {"deferred", "rejected"}
    )
    if authoritative_rejection:
        geometry_json = None
        geometry_type_str = None
        h3_cell = None
        h3_resolution = None
        formatted_address = None
        geocode_type = None
        geocode_result = None

    external_source: str | None = None
    external_id: str | None = None
    if isinstance(geocode_result, dict):
        external_source, external_id = _external_identity_from_geocode_result(
            geocode_result,
            display_name=display_name,
            location_type=location_type_str,
        )

    fingerprint = _fingerprint_for_location(
        project_id=project_id,
        location_type=location_type_str,
        external_source=external_source,
        external_id=external_id,
        geometry_json=geometry_json,
        formatted_address=formatted_address,
        display_name=display_name,
    )
    return _LocationEntryFields(
        display_name=display_name,
        normalized=normalized,
        location_type_str=location_type_str,
        geometry_json=geometry_json,
        geometry_type_str=geometry_type_str,
        h3_cell=h3_cell,
        h3_resolution=h3_resolution,
        formatted_address=formatted_address,
        geocode_type=geocode_type,
        geocode_result=geocode_result,
        authoritative_rejection=authoritative_rejection,
        external_source=external_source,
        external_id=external_id,
        fingerprint=fingerprint,
    )


def _upsert_location(
    session: Session,
    *,
    project_id: int,
    bucket: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    update_existing: bool = True,
) -> LocationUpsertResult | None:
    fields = _location_fields_for_entry(project_id=project_id, bucket=bucket, entry=entry)
    if fields is None:
        return None
    display_name = fields.display_name
    normalized = fields.normalized
    location_type_str = fields.location_type_str
    geometry_json = fields.geometry_json
    geometry_value = geometry_bind_value(session, geometry_json) if geometry_json else None
    geometry_type_str = fields.geometry_type_str
    h3_cell = fields.h3_cell
    h3_resolution = fields.h3_resolution
    formatted_address = fields.formatted_address
    geocode_type = fields.geocode_type
    geocode_result = fields.geocode_result
    authoritative_rejection = fields.authoritative_rejection
    external_source = fields.external_source
    external_id = fields.external_id
    fingerprint = fields.fingerprint
    geocoded = entry.get("geocoded")

    router_audit = _router_audit_from_place_entry(entry)

    # Status semantics (intentionally simple for now):
    # - provisional: extracted/geocoded-ish row but not editorially confirmed
    # - resolved: geocoder returned a usable identity/geometry payload
    # - needs_review: explicit review bucket / partial failures
    # - failed: explicitly not geocoded / hard failure entries
    status = "provisional"
    if bucket == "needs_review":
        status = "needs_review"
    elif geocoded is False:
        status = "failed"
    elif geocode_result and geometry_json:
        status = "resolved"

    loc = _select_existing_substrate_location(
        session,
        project_id=project_id,
        external_source=external_source,
        external_id=external_id,
        fingerprint=fingerprint,
    )

    details = {
        "graph_id": graph_id,
        "run_id": run_id,
        "places_bucket": bucket,
        "raw_entry_id": _raw_entry_id_for_source_details(entry, display_name=display_name),
        **_place_extract_persist_fields_from_entry(entry),
    }

    if loc is None:
        new_loc = SubstrateLocation(
            project_id=project_id,
            name=display_name,
            normalized_name=normalized,
            location_type=location_type_str,
            status=status,
            external_source=external_source,
            external_id=external_id,
            identity_fingerprint=fingerprint,
            geocode_type=geocode_type,
            formatted_address=formatted_address,
            source_kind="agate_geocode",
            source_details_json=details,
            geometry=geometry_value,
            geometry_type=geometry_type_str,
            geometry_json=geometry_json,
            h3_cell=h3_cell,
            h3_resolution=h3_resolution,
            geocode_router_audit_json=router_audit,
        )
        try:
            with session.begin_nested():
                session.add(new_loc)
                session.flush()
        except IntegrityError as exc:
            loc = _fetch_substrate_location_after_unique_violation(
                session,
                project_id=project_id,
                external_source=external_source,
                external_id=external_id,
                identity_fingerprint=fingerprint,
            )
            if loc is None:
                raise RuntimeError(
                    "substrate_location insert collided on unique key but concurrent row "
                    "was not visible; retry the persistence step"
                ) from exc
            loc = _lock_substrate_location_row(session, int(loc.id))  # type: ignore[arg-type]
            _apply_substrate_location_merge(
                loc,
                display_name=display_name,
                normalized=normalized,
                location_type_str=location_type_str,
                status=status,
                external_source=external_source,
                external_id=external_id,
                fingerprint=fingerprint,
                geocode_type=geocode_type,
                formatted_address=formatted_address,
                details=details,
                geometry_value=geometry_value,
                geometry_type_str=geometry_type_str,
                geometry_json=geometry_json,
                geocode_router_audit_json=router_audit,
                h3_cell=h3_cell,
                h3_resolution=h3_resolution,
                clear_geocode_identity=authoritative_rejection,
            )
            session.add(loc)
            session.flush()
        else:
            loc = new_loc
        if bucket != "needs_review":
            _upsert_location_cache(
                session,
                project_id=project_id,
                query_text=display_name,
                location_type=location_type_str,
                entry=entry,
                geocode_type=geocode_type,
                geocode_result=geocode_result if isinstance(geocode_result, dict) else None,
                geometry_json=geometry_json,
                geometry_value=geometry_value,
                geometry_type_str=geometry_type_str,
                formatted_address=formatted_address,
                h3_cell=h3_cell,
                h3_resolution=h3_resolution,
            )
        else:
            _delete_location_cache(
                session,
                project_id=project_id,
                query_text=display_name,
                location_type=location_type_str,
            )
        return LocationUpsertResult(location=loc, created=True, updated=False)

    if not update_existing:
        return LocationUpsertResult(location=loc, created=False, updated=False)

    _apply_substrate_location_merge(
        loc,
        display_name=display_name,
        normalized=normalized,
        location_type_str=location_type_str,
        status=status,
        external_source=external_source,
        external_id=external_id,
        fingerprint=fingerprint,
        geocode_type=geocode_type,
        formatted_address=formatted_address,
        details=details,
        geometry_value=geometry_value,
        geometry_type_str=geometry_type_str,
        geometry_json=geometry_json,
        geocode_router_audit_json=router_audit,
        h3_cell=h3_cell,
        h3_resolution=h3_resolution,
        clear_geocode_identity=authoritative_rejection,
    )
    session.add(loc)
    session.flush()
    if bucket != "needs_review":
        _upsert_location_cache(
            session,
            project_id=project_id,
            query_text=display_name,
            location_type=location_type_str,
            entry=entry,
            geocode_type=geocode_type,
            geocode_result=geocode_result if isinstance(geocode_result, dict) else None,
            geometry_json=geometry_json,
            geometry_value=geometry_value,
            geometry_type_str=geometry_type_str,
            formatted_address=formatted_address,
            h3_cell=h3_cell,
            h3_resolution=h3_resolution,
        )
    else:
        _delete_location_cache(
            session,
            project_id=project_id,
            query_text=display_name,
            location_type=location_type_str,
        )
    return LocationUpsertResult(location=loc, created=False, updated=True)
