"""Tests for ``api.processed_item.overlay.validate``."""

from __future__ import annotations

import pytest
from api.processed_item.overlay.validate import (
    OverlayGeometryValidationError,
    validate_processed_item_overlay_geometry,
)


def test_validate_accepts_empty_locations() -> None:
    validate_processed_item_overlay_geometry({})
    validate_processed_item_overlay_geometry({"locations": {}})


def test_validate_rejects_bad_point() -> None:
    with pytest.raises(OverlayGeometryValidationError):
        validate_processed_item_overlay_geometry(
            {
                "locations": {
                    "by_anchor": {
                        "a": {
                            "geocode": {
                                "result": {"geometry": {"type": "Point", "coordinates": [200, 0]}}
                            }
                        }
                    }
                }
            }
        )


def test_validate_accepts_valid_polygon_ring() -> None:
    ring = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    validate_processed_item_overlay_geometry(
        {
            "locations": {
                "by_anchor": {
                    "a": {
                        "geocode": {
                            "result": {
                                "geometry": {"type": "Polygon", "coordinates": [ring]},
                            }
                        }
                    }
                }
            }
        }
    )


def test_validate_user_added_location_geometry() -> None:
    ring = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    validate_processed_item_overlay_geometry(
        {
            "locations": {
                "user_added": [
                    {
                        "id": "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        "location": {
                            "description": "manual",
                            "geocode": {
                                "result": {
                                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                                }
                            },
                        },
                    }
                ]
            }
        }
    )
