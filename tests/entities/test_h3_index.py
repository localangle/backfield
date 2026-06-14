"""Tests for native H3 index derivation from GeoJSON geometry."""

from __future__ import annotations

import pytest
from backfield_entities.geo.h3_index import POINT_H3_RESOLUTION, derive_h3_index

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}


def test_derive_h3_index_returns_none_for_missing_geometry() -> None:
    assert derive_h3_index(None) is None
    assert derive_h3_index({}) is None


def test_derive_h3_index_uses_block_resolution_for_points() -> None:
    result = derive_h3_index(CHICAGO_POINT)
    assert result is not None
    assert result.h3_resolution == POINT_H3_RESOLUTION
    assert isinstance(result.h3_cell, str)
    assert len(result.h3_cell) > 0


def test_derive_h3_index_uses_coarser_resolution_for_large_polygons() -> None:
    city_bbox = {
        "type": "Polygon",
        "coordinates": [
            [
                [-87.9, 41.6],
                [-87.5, 41.6],
                [-87.5, 42.0],
                [-87.9, 42.0],
                [-87.9, 41.6],
            ]
        ],
    }
    result = derive_h3_index(city_bbox)
    assert result is not None
    assert result.h3_resolution < POINT_H3_RESOLUTION


def test_derive_h3_index_supports_bbox_style_polygon_coordinates() -> None:
    bbox_polygon = {
        "type": "Polygon",
        "coordinates": [-87.9, 41.6, -87.5, 42.0],
    }
    result = derive_h3_index(bbox_polygon)
    assert result is not None
    assert result.h3_resolution < POINT_H3_RESOLUTION


def test_derive_h3_index_parent_cells_are_derivable() -> None:
    h3 = pytest.importorskip("h3")
    result = derive_h3_index(CHICAGO_POINT)
    assert result is not None
    parent = h3.cell_to_parent(result.h3_cell, result.h3_resolution - 1)
    assert isinstance(parent, str)
    assert parent != result.h3_cell
