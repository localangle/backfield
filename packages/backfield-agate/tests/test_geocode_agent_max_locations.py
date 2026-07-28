"""Tests for GeocodeAgent maxLocations overflow handling."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from agate_nodes.geocode_agent.location_limits import (
    location_needs_review_entry,
    split_locations_for_geocoding,
)


def _warm_geocode_import_graph() -> None:
    from agate_runtime.nodes.geocode_agent import run_geocode_agent as _run_geocode_agent

    del _run_geocode_agent


def _location(full: str) -> dict[str, object]:
    return {
        "original_text": full,
        "location": {"full": full, "type": "place", "components": {}},
    }


def test_geocode_agent_default_max_locations_is_200() -> None:
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import GeocodeAgentParams

    assert GeocodeAgentParams().maxLocations == 200


def test_split_locations_for_geocoding_keeps_all_when_under_limit() -> None:
    rows = [_location(f"School {idx}, IL") for idx in range(5)]
    to_process, overflow = split_locations_for_geocoding(rows, 200)
    assert to_process == rows
    assert overflow == []


def test_split_locations_for_geocoding_overflows_to_needs_review_rows() -> None:
    rows = [_location(f"School {idx}, IL") for idx in range(5)]
    to_process, overflow = split_locations_for_geocoding(rows, 3)
    assert [row["location"]["full"] for row in to_process] == [
        "School 0, IL",
        "School 1, IL",
        "School 2, IL",
    ]
    assert [row["location"]["full"] for row in overflow] == [
        "School 3, IL",
        "School 4, IL",
    ]


def test_location_needs_review_entry_shape() -> None:
    entry = location_needs_review_entry(
        _location("Warren Township High School, Gurnee, IL"),
        "Skipped: exceeded maxLocations limit (200)",
        "max_locations_exceeded",
    )
    assert entry["original_text"] == "Warren Township High School, Gurnee, IL"
    assert entry["location"]["full"] == "Warren Township High School, Gurnee, IL"
    assert "maxLocations" in entry["error"]
    assert entry["reason_code"] == "max_locations_exceeded"


def test_pipeline_accounts_for_country_unsupported_error_and_empty_results() -> None:
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import (
        GeocodeAgentInput,
        GeocodeAgentParams,
        run_geocode_agent_pipeline,
    )
    from agate_runtime.context import AgateEnvContext

    components = {
        "country": {"name": "Canada", "abbr": "CA"},
        "state": {"name": "", "abbr": ""},
        "postal_code": "",
    }
    rows = [
        {
            "original_text": "Canada",
            "location": {"full": "Canada", "type": "country", "components": components},
        },
        {
            "original_text": "Unsupported",
            "location": {"full": "Unsupported", "type": "planet", "components": components},
        },
        {
            "original_text": "Error Place",
            "location": {"full": "Error Place", "type": "place", "components": components},
        },
        {
            "original_text": "Empty Place",
            "location": {"full": "Empty Place", "type": "place", "components": components},
        },
    ]

    async def fake_geocode(**kwargs: object) -> dict[str, object]:
        location_text = str(kwargs["location_text"])
        if location_text == "Error Place":
            raise RuntimeError("provider failed")
        if location_text == "Empty Place":
            return {"places": {"areas": {}, "points": [], "needs_review": []}}
        return {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [{"location": "Canada", "type": "country"}],
                },
                "points": [],
                "needs_review": [],
            }
        }

    async def run_pipeline() -> dict[str, object]:
        with patch(
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
            side_effect=fake_geocode,
        ):
            output = await run_geocode_agent_pipeline(
                GeocodeAgentInput.model_validate({"locations": rows}),
                GeocodeAgentParams(),
                AgateEnvContext(),
            )
        return output.model_dump()

    output = asyncio.run(run_pipeline())
    places = output["places"]
    assert places["areas"]["other"] == [{"location": "Canada", "type": "country"}]
    reviews = places["needs_review"]
    assert {entry["reason_code"] for entry in reviews} == {
        "unsupported_location_type",
        "geocoding_error",
        "empty_geocoding_result",
    }
    by_full = {entry["location"]["full"]: entry for entry in reviews}
    for full in ("Unsupported", "Error Place", "Empty Place"):
        assert by_full[full]["original_text"] == full
        assert by_full[full]["location"]["type"]
        assert by_full[full]["location"]["components"] == components
