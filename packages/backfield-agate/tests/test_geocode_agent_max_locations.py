"""Tests for GeocodeAgent maxLocations overflow handling."""

from __future__ import annotations

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
    )
    assert entry["original_text"] == "Warren Township High School, Gurnee, IL"
    assert entry["location"]["full"] == "Warren Township High School, Gurnee, IL"
    assert "maxLocations" in entry["error"]
