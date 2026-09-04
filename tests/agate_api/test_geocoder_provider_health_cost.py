"""Run estimated-cost helpers for geocoder provider health."""

from __future__ import annotations

from api.routers.runs import _geocoder_health_from_node_outputs, _merge_geocoder_health_maps


def test_merge_geocoder_health_maps_sums_counts() -> None:
    merged: dict[str, dict[str, int]] = {}
    _merge_geocoder_health_maps(
        merged,
        {"pelias": {"auth_error": 3, "rate_limit": 0, "http_error": 0}},
    )
    _merge_geocoder_health_maps(
        merged,
        {"pelias": {"auth_error": 1, "rate_limit": 2, "http_error": 0}},
    )
    assert merged["pelias"]["auth_error"] == 4
    assert merged["pelias"]["rate_limit"] == 2


def test_geocoder_health_from_node_outputs_reads_geocode_agent_contribution() -> None:
    from_outputs = _geocoder_health_from_node_outputs(
        {
            "geo": {
                "places": {},
                "geocoder_provider_health": {
                    "pelias": {"auth_error": 5, "rate_limit": 0, "http_error": 0}
                },
            }
        }
    )
    assert from_outputs["pelias"]["auth_error"] == 5
