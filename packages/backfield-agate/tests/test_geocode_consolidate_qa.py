"""QA helpers on geocode consolidate (region plausibility)."""

from __future__ import annotations

from types import SimpleNamespace

from agate_nodes.geocode_agent.nodes.consolidate import (
    _geocode_region_mismatch_qa,
    _point_entry_without_geometry,
)


def _china_geocode_result() -> SimpleNamespace:
    return SimpleNamespace(
        geocoder="pelias_search",
        result=SimpleNamespace(
            id="geonames:country:1814991",
            processed_str="China",
            geometry=SimpleNamespace(type="Point", coordinates=[105.0, 35.0]),
            confidence={"pelias_layer": "country", "pelias_country_code": "CN"},
        ),
    )


def test_region_mismatch_republic_steel_us_extract_china_result() -> None:
    components = {
        "place": {"name": "Republic Steel"},
        "city": "Chicago",
        "state": {"name": "Illinois", "abbr": "IL"},
        "country": {"name": "United States", "abbr": "US"},
    }
    assert _geocode_region_mismatch_qa(components, "China", _china_geocode_result()) is True


def test_region_mismatch_false_for_chicago_stylebook_hit() -> None:
    components = {
        "city": "Chicago",
        "country": {"abbr": "US"},
    }
    hit = SimpleNamespace(
        geocoder="stylebook",
        result=SimpleNamespace(
            id="stylebook:abc",
            processed_str="Chicago, IL",
            geometry=SimpleNamespace(type="Polygon", coordinates=[]),
            confidence={"canonical_id": "abc"},
        ),
    )
    assert _geocode_region_mismatch_qa(components, "Chicago, IL", hit) is False


def test_point_entry_without_geometry_strips_map_pin() -> None:
    entry = {
        "geocode": {
            "result": {
                "formatted_address": "China",
                "geometry": {"type": "Point", "coordinates": [105, 35]},
            },
        },
    }
    out = _point_entry_without_geometry(entry)
    assert "geometry" not in (out["geocode"]["result"] or {})
