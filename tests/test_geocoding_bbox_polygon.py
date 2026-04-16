"""Bbox-as-Polygon normalization used for Pelias/WOF-style extents."""

from __future__ import annotations

from agate_utils.geocoding.geocoding_types import (
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from worker.substrate_persistence import _geojson_to_wkt


def test_bbox_to_polygon_is_closed_ring_of_lon_lat_pairs() -> None:
    ring = bbox_west_south_east_north_to_polygon_coordinates([-87.8, 41.7, -87.6, 41.9])[0]
    assert len(ring) == 5
    assert ring[0] == ring[-1]
    assert ring[0] == [-87.8, 41.7]
    assert ring[1] == [-87.6, 41.7]
    assert ring[2] == [-87.6, 41.9]
    assert ring[3] == [-87.8, 41.9]


def test_geometry_polygon_accepts_normalized_bbox_coordinates() -> None:
    coords = bbox_west_south_east_north_to_polygon_coordinates([-10.0, -20.0, 10.0, 20.0])
    poly = GeometryPolygon(coordinates=coords)
    assert poly.type == "Polygon"
    assert poly.coordinates == coords


def test_geojson_to_wkt_accepts_polygon_from_bbox_helper() -> None:
    coords = bbox_west_south_east_north_to_polygon_coordinates([-87.8, 41.7, -87.6, 41.9])
    wkt = _geojson_to_wkt({"type": "Polygon", "coordinates": coords})
    assert wkt is not None
    assert wkt.startswith("POLYGON ((")
    assert wkt.endswith("))")
