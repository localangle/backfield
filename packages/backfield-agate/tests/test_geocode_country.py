"""Country dispatch and terminal-output tests."""

from __future__ import annotations

import asyncio

import pytest
from agate_nodes.geocode_agent.nodes.consolidate import consolidate_node
from agate_nodes.geocode_agent.nodes.geocode import (
    orchestrate_external_geocode,
    resolve_cache_or_miss,
)
from agate_nodes.geocode_agent.nodes.route_strategy import route_strategy_node


@pytest.mark.parametrize(
    ("raw_name", "canonical_name", "country_code"),
    [
        ("Canada", "Canada", "CA"),
        ("u.s.a.", "United States", "US"),
        ("IN", "India", "IN"),
    ],
)
def test_recognized_country_is_terminal_without_external_geometry(
    raw_name: str,
    canonical_name: str,
    country_code: str,
) -> None:
    state = {
        "location_text": raw_name,
        "location_type": "country",
        "location_components": {
            "country": {"name": canonical_name, "abbr": country_code},
        },
        "original_text": raw_name,
        "extra_fields": {},
        "use_cache": False,
    }

    asyncio.run(resolve_cache_or_miss(state))
    asyncio.run(route_strategy_node(state))
    asyncio.run(orchestrate_external_geocode(state))
    asyncio.run(consolidate_node(state))

    places = state["final_output"]["places"]
    assert places["needs_review"] == []
    assert places["points"] == []
    assert state.get("geocode_strategy") is None
    assert places["areas"]["other"] == [
        {
            "id": f"iso-country:{country_code}",
            "original_text": raw_name,
            "location": canonical_name,
            "type": "country",
            "description": "Recognized country",
            "country_code": country_code,
            "geocode_disposition": "accepted_authoritative_identity",
        }
    ]


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
