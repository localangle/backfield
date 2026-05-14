"""Validate GeoJSON geometry inside processed-item review overlays (v1).

See ``docs/API.md`` → *Processed item location overlay (v1)* → *Geometry*.
"""

from __future__ import annotations

import math
from typing import Any

_MAX_POSITIONS = 4000
_ALLOWED_TYPES = frozenset({"Point", "Polygon", "MultiPolygon"})


class OverlayGeometryValidationError(ValueError):
    """Raised when overlay JSON contains invalid geometry."""


def _count_positions(coords: Any, depth: int) -> int:
    if depth > 6:
        raise OverlayGeometryValidationError("geometry coordinates nested too deeply")
    if isinstance(coords, (int, float)):
        if not math.isfinite(float(coords)):
            raise OverlayGeometryValidationError("geometry coordinates must be finite numbers")
        return 1
    if not isinstance(coords, list):
        raise OverlayGeometryValidationError("geometry coordinates must be arrays of numbers")
    n = 0
    for item in coords:
        n += _count_positions(item, depth + 1)
    return n


def _validate_ring(ring: list[Any], is_outer: bool) -> None:
    if not isinstance(ring, list) or len(ring) < 1:
        raise OverlayGeometryValidationError("polygon ring must be a non-empty coordinate array")
    for pt in ring:
        if (
            not isinstance(pt, list)
            or len(pt) < 2
            or not isinstance(pt[0], (int, float))
            or not isinstance(pt[1], (int, float))
        ):
            raise OverlayGeometryValidationError("polygon ring points must be [lng, lat] pairs")
        lng, lat = float(pt[0]), float(pt[1])
        if not math.isfinite(lng) or not math.isfinite(lat):
            raise OverlayGeometryValidationError("coordinates must be finite")
        if lng < -180.0 or lng > 180.0 or lat < -90.0 or lat > 90.0:
            raise OverlayGeometryValidationError("coordinates out of geographic bounds")
    if is_outer and len(ring) < 4:
        raise OverlayGeometryValidationError("polygon outer ring must have at least four positions")


def _validate_geometry_dict(g: dict[str, Any]) -> None:
    t = g.get("type")
    if not isinstance(t, str) or t not in _ALLOWED_TYPES:
        raise OverlayGeometryValidationError(
            "geometry type must be Point, Polygon, or MultiPolygon",
        )
    coords = g.get("coordinates")
    npos = _count_positions(coords, 0)
    if npos > _MAX_POSITIONS:
        raise OverlayGeometryValidationError("geometry exceeds maximum coordinate count")

    if t == "Point":
        if not isinstance(coords, list) or len(coords) != 2:
            raise OverlayGeometryValidationError("Point geometry must have coordinates [lng, lat]")
        lng, lat = float(coords[0]), float(coords[1])
        if not math.isfinite(lng) or not math.isfinite(lat):
            raise OverlayGeometryValidationError("coordinates must be finite")
        if lng < -180.0 or lng > 180.0 or lat < -90.0 or lat > 90.0:
            raise OverlayGeometryValidationError("coordinates out of geographic bounds")
        return

    if t == "Polygon":
        if not isinstance(coords, list) or len(coords) < 1:
            raise OverlayGeometryValidationError("Polygon geometry must have at least one ring")
        for i, ring in enumerate(coords):
            if not isinstance(ring, list):
                raise OverlayGeometryValidationError("polygon rings must be coordinate arrays")
            _validate_ring(ring, is_outer=(i == 0))
        return

    # MultiPolygon
    if not isinstance(coords, list) or len(coords) < 1:
        raise OverlayGeometryValidationError("MultiPolygon geometry must list at least one polygon")
    for poly in coords:
        if not isinstance(poly, list) or len(poly) < 1:
            raise OverlayGeometryValidationError("MultiPolygon polygon must contain rings")
        for i, ring in enumerate(poly):
            if not isinstance(ring, list):
                raise OverlayGeometryValidationError("polygon rings must be coordinate arrays")
            _validate_ring(ring, is_outer=(i == 0))


def _maybe_validate_geometry_value(obj: Any) -> None:
    if not isinstance(obj, dict):
        raise OverlayGeometryValidationError("geometry must be an object")
    _validate_geometry_dict(obj)


def _walk_place_dict_for_geometry(d: dict[str, Any]) -> None:
    """Validate any GeoJSON geometry attached to a place-shaped dict."""
    g0 = d.get("geometry")
    if g0 is not None:
        _maybe_validate_geometry_value(g0)
    gc = d.get("geocode")
    if isinstance(gc, dict):
        res = gc.get("result")
        if isinstance(res, dict) and res.get("geometry") is not None:
            _maybe_validate_geometry_value(res.get("geometry"))


def _walk_patch_dict(patch: dict[str, Any]) -> None:
    _walk_place_dict_for_geometry(patch)


def _walk_user_added_row(row: dict[str, Any]) -> None:
    loc = row.get("location")
    if isinstance(loc, dict):
        _walk_place_dict_for_geometry(loc)
    else:
        rest = {k: v for k, v in row.items() if k != "id"}
        if isinstance(rest, dict):
            _walk_place_dict_for_geometry(rest)


def validate_processed_item_overlay_geometry(overlay: dict[str, Any]) -> None:
    """Raise ``OverlayGeometryValidationError`` if any geometry in overlay v1 is invalid."""
    loc_root = overlay.get("locations")
    if not isinstance(loc_root, dict):
        return
    by_anchor = loc_root.get("by_anchor")
    if isinstance(by_anchor, dict):
        for _anchor, patch in by_anchor.items():
            if isinstance(patch, dict):
                _walk_patch_dict(patch)
    ua = loc_root.get("user_added")
    if isinstance(ua, list):
        for row in ua:
            if isinstance(row, dict):
                _walk_user_added_row(row)
