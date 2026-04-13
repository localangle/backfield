"""H3 geometry helpers: cell from GeoJSON, same-cell comparison. Used by canonicalization."""

from typing import Optional, Tuple

from agate_utils.geocoding.h3 import h3_cell


def lat_lon_from_geometry_json(geometry_json: Optional[str]) -> Optional[Tuple[float, float]]:
    """Extract (lat, lon) from GeoJSON string. Returns None if missing or invalid."""
    import json

    from shapely.geometry import Point
    from shapely.geometry import shape as shapely_shape

    if not geometry_json or not geometry_json.strip():
        return None
    try:
        geojson = json.loads(geometry_json) if isinstance(geometry_json, str) else geometry_json
        if not geojson:
            return None
        geom = shapely_shape(geojson)
        if geom is None or geom.is_empty:
            return None
        if isinstance(geom, Point):
            return (float(geom.y), float(geom.x))
        centroid = geom.centroid
        if centroid is None or centroid.is_empty:
            return None
        return (float(centroid.y), float(centroid.x))
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None


def h3_cell_from_geometry(geometry_json: Optional[str], resolution: int = 11) -> Optional[str]:
    """
    Return the H3 cell ID (hex string) for a geometry at the given resolution.
    Uses centroid for non-point geometries. Returns None if geometry is missing or invalid.
    """
    ll = lat_lon_from_geometry_json(geometry_json)
    if ll is None:
        return None
    lat, lon = ll
    return h3_cell(lat, lon, resolution)
