"""Location geometry, cache rows, and durable location upserts for substrate persistence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from backfield_db import SubstrateLocation, SubstrateLocationCache
from sqlmodel import Session, col, select

from worker.substrate_common import _normalize_name, _sha256_hex, _utcnow


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


def _coord_pair_wkt(pair: Any) -> str | None:
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    lon, lat = float(pair[0]), float(pair[1])
    return f"{lon} {lat}"


def _ring_coords_wkt(ring: Any) -> str | None:
    if not isinstance(ring, list) or not ring:
        return None
    pts: list[str] = []
    for pair in ring:
        wkt_pair = _coord_pair_wkt(pair)
        if not wkt_pair:
            return None
        pts.append(wkt_pair)
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return ", ".join(pts)


def _geojson_to_wkt(geometry_json: dict[str, Any]) -> str | None:
    gtype = str(geometry_json.get("type") or "").title()
    coords = geometry_json.get("coordinates")

    try:
        if gtype == "Point":
            pair = _coord_pair_wkt(coords)
            if not pair:
                return None
            return f"POINT ({pair})"

        if gtype == "MultiPoint":
            if not isinstance(coords, list) or not coords:
                return None
            parts: list[str] = []
            for pair in coords:
                wkt_pair = _coord_pair_wkt(pair)
                if not wkt_pair:
                    return None
                parts.append(f"({wkt_pair})")
            return "MULTIPOINT (" + ", ".join(parts) + ")"

        if gtype == "LineString":
            if not isinstance(coords, list) or len(coords) < 2:
                return None
            pts: list[str] = []
            for pair in coords:
                wkt_pair = _coord_pair_wkt(pair)
                if not wkt_pair:
                    return None
                pts.append(wkt_pair)
            return "LINESTRING (" + ", ".join(pts) + ")"

        if gtype == "Polygon":
            if not isinstance(coords, list) or not coords:
                return None
            rings_wkt: list[str] = []
            for ring in coords:
                ring_wkt = _ring_coords_wkt(ring)
                if not ring_wkt:
                    return None
                rings_wkt.append(f"({ring_wkt})")
            return "POLYGON (" + ", ".join(rings_wkt) + ")"

        if gtype == "MultiPolygon":
            if not isinstance(coords, list) or not coords:
                return None
            polys: list[str] = []
            for poly in coords:
                if not isinstance(poly, list) or not poly:
                    return None
                rings_wkt = []
                for ring in poly:
                    ring_wkt = _ring_coords_wkt(ring)
                    if not ring_wkt:
                        return None
                    rings_wkt.append(f"({ring_wkt})")
                polys.append("(" + ", ".join(rings_wkt) + ")")
            return "MULTIPOLYGON (" + ", ".join(polys) + ")"
    except Exception:
        return None

    return None


def _geometry_bind_value(session: Session, geometry_json: dict[str, Any]) -> object | None:
    """Return a dialect-appropriate bind value for `SubstrateLocation.geometry`.

    SQLite tests store `geometry` as plain text and cannot bind GeoAlchemy elements.
    Postgres uses true PostGIS geometry via GeoAlchemy's `WKTElement`.
    """

    wkt = _geojson_to_wkt(geometry_json)
    if not wkt:
        return None

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        from geoalchemy2.elements import WKTElement

        return WKTElement(wkt, srid=4326)

    return wkt

def _cache_fingerprint(*, project_id: int, normalized_query: str, location_type: str | None) -> str:
    return _sha256_hex(
        json.dumps(
            {
                "project_id": project_id,
                "normalized_query": normalized_query,
                "location_type": location_type,
            },
            sort_keys=True,
        )
    )


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
) -> None:
    normalized_query = _normalize_name(query_text)
    if not normalized_query:
        return

    fingerprint = _cache_fingerprint(
        project_id=project_id,
        normalized_query=normalized_query,
        location_type=location_type,
    )

    external_source, external_id = (
        _external_identity_from_geocode_result(geocode_result) if geocode_result else (None, None)
    )

    row = session.exec(
        select(SubstrateLocationCache).where(
            col(SubstrateLocationCache.project_id) == project_id,
            col(SubstrateLocationCache.query_fingerprint) == fingerprint,
        )
    ).first()

    now = _utcnow()
    payload = {
        "places_entry": entry,
        "geocode_result": geocode_result,
    }

    if row is None:
        session.add(
            SubstrateLocationCache(
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
                response_payload_json=payload,
            )
        )
    else:
        row.query_text = query_text
        row.normalized_query = normalized_query
        row.external_source = external_source or row.external_source
        row.external_id = external_id or row.external_id
        row.location_name = query_text
        row.location_type = location_type or row.location_type
        row.geocode_type = geocode_type or row.geocode_type
        row.formatted_address = formatted_address or row.formatted_address
        row.geometry = geometry_value or row.geometry
        row.geometry_type = geometry_type_str or row.geometry_type
        row.geometry_json = geometry_json or row.geometry_json
        row.response_payload_json = payload
        row.updated_at = now
        session.add(row)

    session.flush()


def _external_identity_from_geocode_result(result: dict[str, Any]) -> tuple[str | None, str | None]:
    canonical_id = result.get("canonical_id")
    if canonical_id is not None:
        return "stylebook_location", str(int(canonical_id))

    rid = result.get("id")
    if rid is None:
        return None, None
    rid_str = str(rid)
    if rid_str.startswith("stylebook:"):
        return "stylebook_location", rid_str.removeprefix("stylebook:")
    if rid_str.startswith("wof:"):
        return "wof", rid_str
    if rid_str.startswith("pelias:"):
        return "pelias", rid_str
    if rid_str.startswith("h3:"):
        return "h3", rid_str
    return "geocoder", rid_str


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


def _geometry_parts_from_entry(
    session: Session, entry: dict[str, Any]
) -> tuple[dict[str, Any] | None, object | None, str | None]:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    result = geocode.get("result") if geocode and isinstance(geocode.get("result"), dict) else None
    geometry_json: dict[str, Any] | None = None
    if result and isinstance(result.get("geometry"), dict):
        geometry_json = dict(result["geometry"])
    elif isinstance(entry.get("geometry"), dict):
        geometry_json = dict(entry["geometry"])

    bind_value = _geometry_bind_value(session, geometry_json) if geometry_json else None
    geometry_type = geometry_json.get("type") if geometry_json else None
    geometry_type_str = str(geometry_type) if geometry_type else None
    return geometry_json, bind_value, geometry_type_str


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


def _upsert_location(
    session: Session,
    *,
    project_id: int,
    bucket: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
) -> SubstrateLocation | None:
    display_name = _display_name_for_place_entry(entry)
    normalized = _normalize_name(display_name)
    if not normalized:
        return None

    location_type = entry.get("type")
    location_type_str = str(location_type).lower() if location_type is not None else None

    geocoded = entry.get("geocoded")
    geometry_json, geometry_value, geometry_type_str = _geometry_parts_from_entry(session, entry)
    formatted_address = _formatted_address_from_entry(entry)
    geocode_type, geocode_result = _geocode_meta_from_entry(entry)

    external_source: str | None = None
    external_id: str | None = None
    if isinstance(geocode_result, dict):
        external_source, external_id = _external_identity_from_geocode_result(geocode_result)

    fingerprint = _fingerprint_for_location(
        project_id=project_id,
        location_type=location_type_str,
        external_source=external_source,
        external_id=external_id,
        geometry_json=geometry_json,
        formatted_address=formatted_address,
        display_name=display_name,
    )

    # Status semantics (intentionally simple for now):
    # - provisional: extracted/geocoded-ish row but not editorially confirmed
    # - resolved: geocoder returned a usable identity/geometry payload
    # - needs_review: explicit review bucket / partial failures
    # - failed: explicitly not geocoded / hard failure entries
    status = "provisional"
    if bucket == "needs_review":
        status = "needs_review"
    if geocoded is False:
        status = "failed"
    if geocode_result and geometry_json:
        status = "resolved"

    loc: SubstrateLocation | None = None
    if external_source and external_id:
        loc = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.external_source) == external_source,
                col(SubstrateLocation.external_id) == external_id,
            )
        ).first()

    if loc is None:
        loc = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.identity_fingerprint) == fingerprint,
            )
        ).first()

    now = _utcnow()
    details = {
        "graph_id": graph_id,
        "run_id": run_id,
        "places_bucket": bucket,
        "raw_entry_id": entry.get("id"),
        **_place_extract_persist_fields_from_entry(entry),
    }

    if loc is None:
        loc = SubstrateLocation(
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
        )
        session.add(loc)
        session.flush()
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
        )
        return loc

    loc.name = display_name
    loc.normalized_name = normalized
    loc.location_type = location_type_str or loc.location_type
    loc.status = status
    loc.external_source = external_source or loc.external_source
    loc.external_id = external_id or loc.external_id
    loc.identity_fingerprint = fingerprint
    loc.geocode_type = geocode_type or loc.geocode_type
    loc.formatted_address = formatted_address or loc.formatted_address
    loc.source_kind = "agate_geocode"
    prev_details = loc.source_details_json if isinstance(loc.source_details_json, dict) else {}
    loc.source_details_json = {**prev_details, **details}
    loc.geometry = geometry_value or loc.geometry
    loc.geometry_type = geometry_type_str or loc.geometry_type
    loc.geometry_json = geometry_json or loc.geometry_json
    loc.updated_at = now
    session.add(loc)
    session.flush()
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
    )
    return loc
