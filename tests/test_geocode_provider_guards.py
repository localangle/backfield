"""Nominatim bbox order and Geocodio accuracy helpers."""

from __future__ import annotations

from types import SimpleNamespace

from agate_utils.geocoding.geocodio import is_acceptable_geocodio_accuracy
from agate_utils.geocoding.nominatim import NominatimGeocoder


def test_nominatim_bbox_uses_south_north_west_east_order() -> None:
    geocoder = NominatimGeocoder(user_agent="agate-test/1.0")
    location = SimpleNamespace(
        address="Broadway Business Park, Columbia, MO",
        latitude=38.9536168,
        longitude=-92.3846783,
        raw={
            "place_id": 1,
            "formatted_address": "Broadway Business Park, Columbia, MO",
            "class": "landuse",
            "type": "retail",
            # Nominatim order: [south, north, west, east]
            "boundingbox": ["38.9527085", "38.9551404", "-92.3877791", "-92.3808783"],
        },
    )
    result = geocoder._location_to_result(location, "Broadway Business Park, Columbia, MO")
    assert result is not None
    assert result.result is not None
    assert result.result.geometry.type == "Polygon"
    ring = result.result.geometry.coordinates[0]
    assert ring[0] == [-92.3877791, 38.9527085]
    assert ring[1] == [-92.3808783, 38.9527085]
    assert ring[2] == [-92.3808783, 38.9551404]
    assert ring[3] == [-92.3877791, 38.9551404]
    assert ring[0] == ring[-1]


def test_geocodio_accuracy_allowlist() -> None:
    assert is_acceptable_geocodio_accuracy({"accuracy_type": "rooftop", "accuracy": 1.0})
    assert is_acceptable_geocodio_accuracy(
        {"accuracy_type": "range_interpolation", "accuracy": 0.9}
    )
    assert is_acceptable_geocodio_accuracy({"accuracy_type": "intersection", "accuracy": 0.85})
    assert not is_acceptable_geocodio_accuracy({"accuracy_type": "place", "accuracy": 0.5})
    assert not is_acceptable_geocodio_accuracy({"accuracy_type": "street_center", "accuracy": 0.7})
    assert not is_acceptable_geocodio_accuracy(
        {"accuracy_type": "nearest_rooftop_match", "accuracy": 0.89}
    )
    assert not is_acceptable_geocodio_accuracy({"accuracy_type": "postal_code", "accuracy": 1.0})
    assert not is_acceptable_geocodio_accuracy({"accuracy_type": "rooftop", "accuracy": 0.5})
