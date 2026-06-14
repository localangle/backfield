"""Derive native H3 cell metadata from GeoJSON geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

POINT_H3_RESOLUTION = 11
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class H3IndexResult:
    h3_cell: str
    h3_resolution: int


def _latlng_to_cell(lat: float, lon: float, resolution: int) -> str:
    from h3 import latlng_to_cell

    return str(latlng_to_cell(lat, lon, resolution))


def _collect_lon_lat_pairs(coords: Any, pairs: list[tuple[float, float]]) -> None:
    if isinstance(coords, (list, tuple)):
        if (
            len(coords) >= 2
            and isinstance(coords[0], (int, float))
            and isinstance(coords[1], (int, float))
        ):
            pairs.append((float(coords[0]), float(coords[1])))
            return
        for item in coords:
            _collect_lon_lat_pairs(item, pairs)


def _bbox_from_geometry(geometry_json: dict[str, Any]) -> tuple[float, float, float, float] | None:
    gtype = str(geometry_json.get("type") or "")
    coords = geometry_json.get("coordinates")
    if not coords:
        return None

    if (
        gtype == "Polygon"
        and isinstance(coords, list)
        and len(coords) == 4
        and all(isinstance(value, (int, float)) for value in coords)
    ):
        west, south, east, north = (
            float(coords[0]),
            float(coords[1]),
            float(coords[2]),
            float(coords[3]),
        )
        return west, south, east, north

    pairs: list[tuple[float, float]] = []
    _collect_lon_lat_pairs(coords, pairs)
    if not pairs:
        return None
    lons = [pair[0] for pair in pairs]
    lats = [pair[1] for pair in pairs]
    return min(lons), min(lats), max(lons), max(lats)


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


def _representative_lat_lon(geometry_json: dict[str, Any]) -> tuple[float, float] | None:
    gtype = str(geometry_json.get("type") or "")
    coords = geometry_json.get("coordinates")
    if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[1]), float(coords[0])

    bbox = _bbox_from_geometry(geometry_json)
    if bbox is None:
        return None
    west, south, east, north = bbox
    return (south + north) / 2.0, (west + east) / 2.0


def _max_extent_km(geometry_json: dict[str, Any]) -> float | None:
    bbox = _bbox_from_geometry(geometry_json)
    if bbox is None:
        return None
    west, south, east, north = bbox
    width_km = _haversine_km(west, south, east, south)
    height_km = _haversine_km(west, south, west, north)
    return max(width_km, height_km)


def _resolution_for_extent_km(max_extent_km: float) -> int:
    """Map footprint size to a native H3 resolution (coarser cells for larger areas)."""
    thresholds: tuple[tuple[float, int], ...] = (
        (50.0, 4),
        (10.0, 5),
        (3.0, 6),
        (1.0, 7),
        (0.3, 8),
        (0.1, 9),
        (0.03, 10),
    )
    for min_extent_km, resolution in thresholds:
        if max_extent_km > min_extent_km:
            return resolution
    return POINT_H3_RESOLUTION


def _native_resolution(geometry_json: dict[str, Any]) -> int:
    gtype = str(geometry_json.get("type") or "")
    if gtype == "Point":
        return POINT_H3_RESOLUTION

    max_extent_km = _max_extent_km(geometry_json)
    if max_extent_km is None or max_extent_km <= 0:
        return POINT_H3_RESOLUTION
    return _resolution_for_extent_km(max_extent_km)


def derive_h3_index(geometry_json: dict[str, Any] | None) -> H3IndexResult | None:
    """Return native H3 cell metadata for a GeoJSON geometry, or ``None`` when invalid."""
    if not isinstance(geometry_json, dict):
        return None

    lat_lon = _representative_lat_lon(geometry_json)
    if lat_lon is None:
        return None

    lat, lon = lat_lon
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    resolution = _native_resolution(geometry_json)
    try:
        cell = _latlng_to_cell(lat, lon, resolution)
    except (ImportError, ValueError, TypeError):
        return None

    return H3IndexResult(h3_cell=cell, h3_resolution=resolution)


def apply_h3_fields(
    *,
    h3_cell: str | None = None,
    h3_resolution: int | None = None,
    geometry_json: dict[str, Any] | None = None,
) -> tuple[str | None, int | None]:
    """Resolve H3 metadata from explicit values or derived geometry."""
    if h3_cell and h3_resolution is not None:
        return h3_cell, h3_resolution
    derived = derive_h3_index(geometry_json)
    if derived is None:
        return None, None
    return derived.h3_cell, derived.h3_resolution
