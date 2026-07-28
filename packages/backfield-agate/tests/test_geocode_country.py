"""Country dispatch and terminal-output tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from agate_nodes.geocode_agent.models.area.country import Country
from agate_nodes.geocode_agent.nodes.consolidate import consolidate_node
from agate_nodes.geocode_agent.nodes.geocode import (
    orchestrate_external_geocode,
    resolve_cache_or_miss,
)
from agate_nodes.geocode_agent.nodes.route_strategy import route_strategy_node
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)


@pytest.mark.parametrize(
    ("raw_name", "canonical_name", "country_code"),
    [
        ("Canada", "Canada", "CA"),
        ("u.s.a.", "United States", "US"),
        ("IN", "India", "IN"),
    ],
)
def test_recognized_country_falls_back_to_identity_without_pelias_bbox(
    raw_name: str,
    canonical_name: str,
    country_code: str,
) -> None:
    """Without a Pelias key/hit, countries remain accepted identity-only (no geography)."""
    state = {
        "location_text": raw_name,
        "location_type": "country",
        "location_components": {
            "country": {"name": canonical_name, "abbr": country_code},
        },
        "original_text": raw_name,
        "extra_fields": {},
        "use_cache": False,
        "pelias_api_key": None,
    }

    asyncio.run(resolve_cache_or_miss(state))
    asyncio.run(route_strategy_node(state))
    asyncio.run(orchestrate_external_geocode(state))
    asyncio.run(consolidate_node(state))

    places = state["final_output"]["places"]
    assert places["needs_review"] == []
    assert places["points"] == []
    assert state.get("country_terminal_identity", {}).get("abbr") == country_code
    assert len(places["areas"]["other"]) == 1
    entry = places["areas"]["other"][0]
    assert entry["id"] == f"iso-country:{country_code}"
    assert entry["location"] == canonical_name
    assert entry["type"] == "country"
    assert entry["country_code"] == country_code
    assert entry["geocode_disposition"] == "accepted_authoritative_identity"
    assert "geocode" not in entry
    assert state.get("geocode_strategy") == "no_web_search"


def test_recognized_country_attaches_pelias_bbox_when_available() -> None:
    polygon = GeometryPolygon(
        coordinates=bbox_west_south_east_north_to_polygon_coordinates(
            [-141.0, 41.7, -52.6, 83.1]
        ),
    )
    pelias_result = GeocodingResult(
        geocoder="pelias_structured",
        input_str="Canada",
        result=GeocodingResultData(
            id="whosonfirst:country:85633041",
            processed_str="Canada",
            geometry=polygon,
            confidence={
                "pelias_layer": "country",
                "pelias_country_code": "CA",
                "pelias_has_bbox": True,
                "pelias_bbox": [-141.0, 41.7, -52.6, 83.1],
                "pelias_source": "whosonfirst",
                "pelias_gid": "whosonfirst:country:85633041",
            },
        ),
    )

    state = {
        "location_text": "Canada",
        "location_type": "country",
        "location_components": {
            "country": {"name": "Canada", "abbr": "CA"},
        },
        "original_text": "Canada",
        "extra_fields": {},
        "use_cache": False,
        "pelias_api_key": "test-key",
    }

    async def run() -> None:
        await resolve_cache_or_miss(state)
        await route_strategy_node(state)
        with patch.object(Country, "geocode", new=AsyncMock(return_value=pelias_result)):
            await orchestrate_external_geocode(state)
        await consolidate_node(state)

    asyncio.run(run())

    places = state["final_output"]["places"]
    assert places["needs_review"] == []
    assert len(places["areas"]["other"]) == 1
    entry = places["areas"]["other"][0]
    assert entry["id"] == "iso-country:CA"
    assert entry["geocode_disposition"] == "accepted_with_pelias_boundary"
    assert entry["geocode"]["geocode_type"] == "pelias_structured"
    assert entry["geocode"]["result"]["geometry"]["type"] == "Polygon"


def test_country_model_rejects_mismatched_or_point_only_candidates() -> None:
    model = Country(name="Canada", country="CA")
    point = GeocodingResult(
        geocoder="pelias_search",
        input_str="Canada",
        result=GeocodingResultData(
            id="gid:point",
            processed_str="Canada",
            geometry=GeometryPoint(coordinates=[-106.0, 56.0]),
            confidence={
                "pelias_layer": "country",
                "pelias_country_code": "CA",
                "pelias_has_bbox": False,
            },
        ),
    )
    wrong_code = GeocodingResult(
        geocoder="pelias_search",
        input_str="Canada",
        result=GeocodingResultData(
            id="gid:us",
            processed_str="United States",
            geometry=GeometryPolygon(
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                    [-125.0, 24.0, -66.0, 49.0]
                ),
            ),
            confidence={
                "pelias_layer": "country",
                "pelias_country_code": "US",
                "pelias_has_bbox": True,
                "pelias_bbox": [-125.0, 24.0, -66.0, 49.0],
            },
        ),
    )
    assert model._choose_best_area_candidate([point], expected_layer="country") is None
    assert model._choose_best_area_candidate([wrong_code], expected_layer="country") is None


@pytest.mark.parametrize("raw_name", ["Atlantis", "North Exampleland"])
def test_unknown_country_preserves_raw_name_and_routes_to_specific_review(
    raw_name: str,
) -> None:
    state = {
        "location_text": raw_name,
        "location_type": "country",
        "location_components": {
            "country": {"name": raw_name, "abbr": ""},
        },
        "original_text": raw_name,
        "extra_fields": {},
        "use_cache": False,
    }

    asyncio.run(resolve_cache_or_miss(state))
    asyncio.run(route_strategy_node(state))
    asyncio.run(orchestrate_external_geocode(state))
    asyncio.run(consolidate_node(state))

    review = state["final_output"]["places"]["needs_review"]
    assert len(review) == 1
    assert review[0]["location"] == raw_name
    assert review[0]["reason_code"] == "country_identity_unresolved"
    assert review[0]["geocode_disposition"] == "needs_country_identity_review"
    assert state["location_components"]["country"] == {"name": raw_name, "abbr": ""}
