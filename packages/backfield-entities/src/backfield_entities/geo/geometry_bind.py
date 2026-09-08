"""Convert GeoJSON to a dialect-appropriate bind value for location PostGIS columns."""

from __future__ import annotations

from typing import Any, Protocol

from backfield_entities.geo.h3_index import apply_h3_fields
from sqlmodel import Session

# ``str.title()`` mangles camelCase GeoJSON types (``MultiPolygon`` → ``Multipolygon``).
_GEOJSON_TYPE_BY_KEY: dict[str, str] = {
    "point": "Point",
    "multipoint": "MultiPoint",
    "linestring": "LineString",
    "multilinestring": "MultiLineString",
    "polygon": "Polygon",
    "multipolygon": "MultiPolygon",
}


class HasLocationGeometry(Protocol):
    geometry: object | None
    geometry_json: dict | None
    geometry_type: str | None
    h3_cell: str | None
    h3_resolution: int | None


class GeometryBindError(ValueError):
    """GeoJSON was provided but could not be converted to a PostGIS bind value."""


def normalize_geojson_type(raw: object | None) -> str | None:
    """Return the canonical GeoJSON geometry type, or ``None`` when unrecognized."""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower().replace("_", "").replace(" ", "")
    return _GEOJSON_TYPE_BY_KEY.get(key)


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


def geojson_to_wkt(geometry_json: dict[str, Any]) -> str | None:
    """Return WKT for a GeoJSON geometry, or ``None`` when the shape is invalid."""
    gtype = normalize_geojson_type(geometry_json.get("type"))
    if gtype is None:
        return None
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

        if gtype == "MultiLineString":
            if not isinstance(coords, list) or not coords:
                return None
            lines: list[str] = []
            for line in coords:
                if not isinstance(line, list) or len(line) < 2:
                    return None
                pts = []
                for pair in line:
                    wkt_pair = _coord_pair_wkt(pair)
                    if not wkt_pair:
                        return None
                    pts.append(wkt_pair)
                lines.append("(" + ", ".join(pts) + ")")
            return "MULTILINESTRING (" + ", ".join(lines) + ")"

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


def geometry_bind_value(session: Session, geometry_json: dict[str, Any]) -> object | None:
    """Return a dialect-appropriate bind value for a location ``geometry`` column.

    SQLite tests store ``geometry`` as plain text and cannot bind GeoAlchemy elements.
    Postgres uses true PostGIS geometry via GeoAlchemy's ``WKTElement``.
    """
    wkt = geojson_to_wkt(geometry_json)
    if not wkt:
        return None

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        from geoalchemy2.elements import WKTElement

        return WKTElement(wkt, srid=4326)

    return wkt


def assign_geojson_geometry(
    session: Session,
    row: HasLocationGeometry,
    geometry_json: dict[str, Any] | None,
) -> None:
    """Write GeoJSON, PostGIS, type, and H3 onto a canonical or saved-place row.

    When ``geometry_json`` is provided it must convert to a PostGIS bind value; otherwise
    this raises :class:`GeometryBindError` so callers never leave GeoJSON/H3 updated while
    ``geometry`` is cleared (article geo-search keys off PostGIS).
    """
    if geometry_json is None:
        row.geometry_json = None
        row.geometry = None
        row.geometry_type = None
        row.h3_cell = None
        row.h3_resolution = None
        return

    copied = dict(geometry_json)
    bind = geometry_bind_value(session, copied)
    if bind is None:
        raise GeometryBindError(
            f"Could not convert GeoJSON to PostGIS geometry (type={copied.get('type')!r})."
        )

    row.geometry_json = copied
    gt = normalize_geojson_type(copied.get("type")) or copied.get("type")
    row.geometry_type = str(gt) if gt else None
    row.geometry = bind
    cell, resolution = apply_h3_fields(geometry_json=copied)
    row.h3_cell = cell
    row.h3_resolution = resolution
