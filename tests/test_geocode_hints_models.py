"""Unit tests for geocode_hints wiring on geography models and Address picker."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from agate_nodes.geocode_agent.models.area.city import City
from agate_nodes.geocode_agent.models.area.span import Span
from agate_nodes.geocode_agent.models.point.address import Address
from agate_nodes.geocode_agent.models.point.intersection import Intersection
from agate_nodes.geocode_agent.nodes.geocode import _create_model
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
)


def _state(**kwargs: object) -> dict:
    base: dict = {
        "location_type": "city",
        "location_text": "",
        "original_text": "Story mention.",
        "extra_fields": {},
    }
    base.update(kwargs)
    return base


def test_create_model_region_includes_geocode_hints_in_context() -> None:
    state = _state(
        location_type="region_city",
        location_text="North industrial pocket",
        extra_fields={
            "description": "Near river",
            "geocode_hints": "East of downtown per earlier graf.",
        },
    )
    model = _create_model("region_city", "North industrial pocket", {}, state)
    assert model.additional_context is not None
    assert "Geocode hints: East of downtown per earlier graf." in model.additional_context


def test_create_model_natural_includes_geocode_hints() -> None:
    state = _state(
        location_type="natural",
        location_text="Blue Lake",
        location_components={
            "city": "Duluth",
            "state": {"name": "Minnesota", "abbr": "MN"},
            "place": {"name": "Blue Lake", "natural": True, "addressable": False},
        },
        geocode_hints="Smaller kettle lake, not the national park.",
    )
    model = _create_model("natural", "Blue Lake", state["location_components"], state)
    assert model.additional_context
    assert "Geocode hints: Smaller kettle lake" in model.additional_context


def test_create_model_street_road_sets_geocode_hints() -> None:
    state = _state(
        location_type="street_road",
        location_text="8th Ave S",
        location_components={
            "street_road": {"name": "8th Ave S", "boundary": "Chicago, IL"},
            "city": "Chicago",
            "state": {"abbr": "IL"},
        },
        geocode_hints="South Side robbery corridor.",
    )
    model = _create_model("street_road", "8th Ave S", state["location_components"], state)
    assert model._geocode_hints == "South Side robbery corridor."


def test_create_model_intersection_sets_geocode_hints() -> None:
    state = _state(
        location_type="intersection_road",
        location_text="A and B",
        geocode_hints="Crash scene at signalized corner.",
    )
    model = _create_model("intersection_road", "A and B", {}, state)
    assert model._geocode_hints == "Crash scene at signalized corner."


def test_create_model_address_sets_hints_and_original() -> None:
    state = _state(
        location_type="address",
        location_text="100 Main",
        location_components={"address": "100 Main St", "city": "Madison", "state": {"abbr": "WI"}},
        original_text="Fire at 100 Main St.",
        geocode_hints="Apartment row on east side of block.",
    )
    model = _create_model("address", "100 Main", state["location_components"], state)
    assert model._original_text == "Fire at 100 Main St."
    assert model._geocode_hints == "Apartment row on east side of block."


def test_span_city_endpoint_sets_geocode_hints_on_city() -> None:
    async def _run() -> None:
        span = Span(
            name="s",
            span={"start": {"type": "city", "location": "Madison, WI"}},
            country="US",
        )
        span._geocode_hints = "city hint"
        with patch.object(City, "geocode", new=AsyncMock(return_value=None)):
            city, _pt = await span._geocode_city_endpoint("Madison, WI", "pk", None, None)
        assert city is not None
        assert getattr(city, "_geocode_hints", None) == "city hint"

    asyncio.run(_run())


def test_span_intersection_endpoint_inherits_parent_geocode_hints() -> None:
    async def _run() -> None:
        span = Span(
            name="s",
            span={"start": {"type": "intersection", "location": "Road A and Road B"}},
            country="US",
        )
        span._geocode_hints = "parent hint"
        with patch.object(Intersection, "geocode", new=AsyncMock(return_value=None)):
            im, _pt = await span._geocode_intersection_endpoint("Road A and Road B", None, "sk")
        assert im is not None
        assert im._geocode_hints == "parent hint"

    asyncio.run(_run())


def test_create_model_span_propagates_geocode_hints() -> None:
    state = _state(
        location_type="span",
        location_text="Hennepin span",
        location_components={
            "span": {
                "start": {"type": "city", "location": "Minneapolis, MN"},
                "end": {
                    "type": "intersection",
                    "location": "Hennepin Ave and Lake St, Minneapolis, MN",
                },
            }
        },
        geocode_hints="Parade route segment.",
    )
    span = _create_model("span", "Hennepin span", state["location_components"], state)
    assert span._geocode_hints == "Parade route segment."


def test_address_pick_pelias_candidate_with_llm_selects_second() -> None:
    def _mk(label: str, lon: float, lat: float) -> GeocodingResult:
        return GeocodingResult(
            geocoder="pelias_search",
            input_str="q",
            result=GeocodingResultData(
                id=f"id-{label}",
                processed_str=label,
                geometry=GeometryPoint(type="Point", coordinates=[lon, lat]),
                confidence={},
            ),
        )

    cands = [_mk("A", -93.0, 45.0), _mk("B", -93.1, 45.1), _mk("C", -93.2, 45.2)]
    addr = Address(name="100 Main", city="Madison", state_abbr="WI", country="US")
    addr._original_text = "Event at 100 Main near campus."
    addr._geocode_hints = "Prefer the B candidate."

    def _fake_llm(*_a: object, **_k: object) -> str:
        return json.dumps({"selected_index": 2, "confidence": 90})

    with patch("agate_nodes.geocode_agent.models.point.address.call_llm", _fake_llm):
        picked = addr._pick_pelias_candidate_with_llm(cands, "100 Main, Madison, WI", "sk-test")

    assert picked is not None
    assert picked.result and picked.result.processed_str == "B"


def test_address_geocode_uses_candidates_when_structured_fails() -> None:
    async def _run() -> None:
        addr = Address(name="100 Main", city="Madison", state_abbr="WI", country="US")
        addr._original_text = "Story."
        addr._geocode_hints = "Pick second."

        def _mk(label: str, lon: float, lat: float) -> GeocodingResult:
            return GeocodingResult(
                geocoder="pelias_search",
                input_str="q",
                result=GeocodingResultData(
                    id=f"id-{label}",
                    processed_str=label,
                    geometry=GeometryPoint(type="Point", coordinates=[lon, lat]),
                    confidence={},
                ),
            )

        cands = [_mk("one", -89.4, 43.1), _mk("two", -89.41, 43.11), _mk("three", -89.42, 43.12)]

        async def _no_structured(**_k: object) -> None:
            return None

        async def _cands(*_a: object, **_k: object):
            return cands

        def _fake_llm(*_a: object, **_k: object) -> str:
            return json.dumps({"selected_index": 2, "confidence": 85})

        with (
            patch(
                "agate_nodes.geocode_agent.models.point.address.pelias_structured",
                new=AsyncMock(side_effect=_no_structured),
            ),
            patch(
                "agate_nodes.geocode_agent.models.point.address.geocode_search_candidates",
                new=AsyncMock(side_effect=_cands),
            ),
            patch("agate_nodes.geocode_agent.models.point.address.call_llm", _fake_llm),
        ):
            result = await addr.geocode(
                pelias_api_key="pk-test",
                geocodio_api_key=None,
                openai_api_key="sk-test",
            )

        assert result is not None
        assert result.result and result.result.processed_str == "two"

    asyncio.run(_run())
