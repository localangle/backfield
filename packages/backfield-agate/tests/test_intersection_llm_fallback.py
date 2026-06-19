"""Intersection LLM point-estimate fallback."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agate_nodes.geocode_agent.models.point.intersection import Intersection
from agate_nodes.geocode_agent.nodes.consolidate import consolidate_node


def test_intersection_geocode_falls_back_to_llm_after_external_failures() -> None:
    intersection = Intersection(
        name="North and Damen Avenues, Chicago, IL",
        city="Chicago",
        state_abbr="IL",
        country="US",
    )
    intersection._original_text = "crash at North and Damen"
    intersection._geocode_hints = "Chicago neighborhood context"

    llm_payload = '{"lat": 41.918, "lon": -87.677, "confidence": 72, "reasoning": "Known crossing"}'

    async def run() -> None:
        with (
            patch.object(intersection, "_try_geocodio", return_value=None),
            patch.object(intersection, "_try_overpass", new=AsyncMock(return_value=None)),
            patch(
                "agate_nodes.geocode_agent.models.point.intersection.call_llm",
                return_value=llm_payload,
            ),
        ):
            result = await intersection.geocode(
                geocodio_api_key="geo-key",
                openai_api_key="openai-key",
            )

        assert result is not None
        assert result.geocoder == "intersection_llm_estimate"
        assert result.result.geometry.type == "Point"
        assert result.result.geometry.coordinates == [-87.677, 41.918]
        assert result.result.confidence["method"] == "llm_intersection_estimate"

    asyncio.run(run())


def test_intersection_llm_fallback_rejects_low_confidence() -> None:
    intersection = Intersection(name="Foo and Bar, Chicago, IL")
    llm_payload = '{"lat": 41.9, "lon": -87.6, "confidence": 20, "reasoning": "unsure"}'

    async def run() -> None:
        with (
            patch.object(intersection, "_try_geocodio", return_value=None),
            patch.object(intersection, "_try_overpass", new=AsyncMock(return_value=None)),
            patch(
                "agate_nodes.geocode_agent.models.point.intersection.call_llm",
                return_value=llm_payload,
            ),
        ):
            result = await intersection.geocode(openai_api_key="openai-key")

        assert result is None

    asyncio.run(run())


def test_consolidate_routes_llm_intersection_estimate_to_needs_review() -> None:
    geocoding_result = SimpleNamespace(
        geocoder="intersection_llm_estimate",
        result=SimpleNamespace(
            id="intersection_llm:abc",
            processed_str="North and Damen Avenues, Chicago, IL (LLM intersection estimate)",
            geometry=SimpleNamespace(type="Point", coordinates=[-87.677, 41.918]),
            confidence={"method": "llm_intersection_estimate", "confidence": 72},
        ),
    )
    state = {
        "location_type": "intersection_road",
        "location_text": "North and Damen Avenues, Chicago, IL",
        "original_text": "crash at North and Damen",
        "extra_fields": {},
        "location_components": {
            "city": "Chicago",
            "state": {"abbr": "IL"},
        },
        "geocoding_result": geocoding_result,
        "advanced_quiet_logs": True,
    }

    async def run() -> None:
        with (
            patch(
                "agate_nodes.geocode_agent.nodes.consolidate.compute_emit_location_line",
                new=AsyncMock(return_value="North and Damen Avenues, Chicago, IL"),
            ),
            patch(
                "agate_nodes.geocode_agent.nodes.consolidate.maybe_upgrade_intersection_to_named_place",
                new=AsyncMock(return_value=("North and Damen Avenues, Chicago, IL", False)),
            ),
        ):
            out = await consolidate_node(state)

        needs_review = out["final_output"]["places"]["needs_review"]
        assert len(needs_review) == 1
        assert needs_review[0]["geocode_qa_code"] == "llm_intersection_estimate"
        assert out["final_output"]["places"]["points"] == []

    asyncio.run(run())
