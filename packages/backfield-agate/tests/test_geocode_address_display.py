"""Address display identity guards for GeocodeAgent output."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from agate_nodes.geocode_agent.nodes.consolidate import consolidate_node
from agate_nodes.geocode_agent.nodes.emit_location_line import compute_emit_location_line


def _address_state() -> dict:
    return {
        "location_type": "address",
        "location_text": "125 North Main Street",
        "location_components": {
            "address": "125 North Main Street",
            "city": "Springfield",
            "state": {"name": "Illinois", "abbr": "IL"},
            "country": {"name": "United States", "abbr": "US"},
        },
        "original_text": "The hearing was held at 125 North Main Street.",
        "geocode_hints": "Springfield, Illinois",
        "openai_api_key": "test-key",
        "evaluation_llm_model": "test-model",
    }


@pytest.mark.parametrize(
    "emitted,polished",
    [
        ("Springfield, IL", "Springfield, IL"),
        ("Civic Center, Springfield, IL", "Downtown, Springfield, IL"),
        ("126 North Main Street, Springfield, IL", "126 N Main St, Springfield, IL"),
        ("125 Oak Street, Springfield, IL", "125 Oak St, Springfield, IL"),
    ],
)
def test_address_display_falls_back_when_llm_substitutes_broader_place(
    emitted: str,
    polished: str,
) -> None:
    state = _address_state()

    async def run() -> str:
        with patch(
            "agate_nodes.geocode_agent.nodes.emit_location_line.call_llm",
            side_effect=[
                f'{{"location": "{emitted}"}}',
                f'{{"location": "{polished}"}}',
            ],
        ):
            return await compute_emit_location_line(
                state,
                formatted_address="125 N Main St, Springfield, IL 62701",
            )

    assert asyncio.run(run()) == "125 North Main Street, Springfield, IL"


def test_address_display_accepts_normalized_street_spelling_with_exact_number() -> None:
    state = _address_state()

    async def run() -> str:
        with patch(
            "agate_nodes.geocode_agent.nodes.emit_location_line.call_llm",
            side_effect=[
                '{"location": "125 N Main St, Springfield, IL"}',
                '{"location": "125 North Main Street, Springfield, IL"}',
            ],
        ):
            return await compute_emit_location_line(
                state,
                formatted_address="125 N Main St, Springfield, IL 62701",
            )

    assert asyncio.run(run()) == "125 North Main Street, Springfield, IL"


def test_consolidation_retains_address_extraction_type_after_named_display_upgrade() -> None:
    state = {
        **_address_state(),
        "geocoding_result": SimpleNamespace(
            geocoder="pelias_search",
            result=SimpleNamespace(
                id="pelias:address:125-main",
                processed_str="125 N Main St, Springfield, IL",
                geometry=SimpleNamespace(type="Point", coordinates=[-89.6436, 39.8017]),
                confidence={
                    "pelias_layer": "address",
                    "pelias_region_a": "IL",
                    "pelias_country_code": "US",
                },
            ),
        ),
        "extra_fields": {},
        "advanced_quiet_logs": True,
    }

    async def run() -> dict:
        with (
            patch(
                "agate_nodes.geocode_agent.nodes.consolidate.compute_emit_location_line",
                new=AsyncMock(return_value="125 North Main Street, Springfield, IL"),
            ),
            patch(
                "agate_nodes.geocode_agent.nodes.consolidate.maybe_upgrade_address_to_named_place",
                new=AsyncMock(
                    return_value=("125 North Main Street, Springfield, IL", True)
                ),
            ),
        ):
            return await consolidate_node(state)

    output = asyncio.run(run())
    points = output["final_output"]["places"]["points"]
    assert len(points) == 1
    assert points[0]["type"] == "address"
