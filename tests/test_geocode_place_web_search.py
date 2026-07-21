"""Tests for Place web search gating (Brave then DuckDuckGo)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from agate_nodes.geocode_agent.models.point.place import Place
from agate_utils.search import SearchResponse, SearchResult


def _sample_results(query: str) -> SearchResponse:
    return SearchResponse(
        success=True,
        results=[
            SearchResult(title="t", snippet="s", url="https://example.com"),
        ],
        query=query,
    )


def test_place_search_skipped_when_allow_web_false() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    with (
        patch("agate_nodes.geocode_agent.models.point.place.brave_place_search") as brave,
        patch("agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo") as ddg,
    ):
        out = place._search_for_address(
            "brave-key",
            "",
            "sk-openai",
            allow_web_search=False,
        )
    assert out is None
    brave.assert_not_called()
    ddg.assert_not_called()


def test_place_search_ddg_when_no_brave_key() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    with (
        patch.object(place, "_generate_search_query", return_value="Cafe St Paul address"),
        patch("agate_nodes.geocode_agent.models.point.place.brave_place_search") as brave,
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=_sample_results("Cafe St Paul address"),
        ) as ddg,
    ):
        out = place._search_for_address(None, "", "sk", allow_web_search=True)
    brave.assert_not_called()
    ddg.assert_called_once()
    assert out is not None
    assert out.success


def test_place_search_brave_hit_skips_ddg() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    brave_resp = _sample_results("q1")
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=brave_resp,
        ) as brave,
        patch("agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo") as ddg,
    ):
        out = place._search_for_address("k", "", "sk", allow_web_search=True)
    brave.assert_called_once()
    ddg.assert_not_called()
    assert out == brave_resp


def test_place_search_brave_empty_then_ddg() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    empty = SearchResponse(success=True, results=[], query="q1")
    ddg_resp = _sample_results("q1")
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=empty,
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=ddg_resp,
        ) as ddg,
    ):
        out = place._search_for_address("k", "", "sk", allow_web_search=True)
    ddg.assert_called_once()
    assert out == ddg_resp


def test_place_prep_includes_full_address_alias() -> None:
    place = Place(name="Spyhouse", city="St Paul", state_abbr="MN", country="US")
    prep = place._prep()
    assert prep.get("full_address") == prep.get("full_place")
    assert "Spyhouse" in (prep.get("full_address") or "")


def test_place_prep_prefers_street_address_for_structured_query() -> None:
    place = Place(
        name="Spyhouse",
        city="St Paul",
        state_abbr="MN",
        country="US",
        street_address="400 Sibley St",
    )
    prep = place._prep()
    assert prep["pelias_structured"]["address"] == "400 Sibley St"
    assert "Spyhouse" in prep["full_address"]
    assert "400 Sibley St" in prep["full_address"]


def test_place_geocode_does_not_skip_when_marked_not_addressable() -> None:
    """type=place must still attempt Pelias even if addressability was false."""
    place = Place(name="Lincoln Park Zoo", city="Chicago", state_abbr="IL", country="US")
    place._input_addressability = False
    sentinel = object()
    with (
        patch(
            "agate_nodes.geocode_agent.models.point.place.has_llm_auth",
            return_value=True,
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.address.Address.geocode",
            new_callable=AsyncMock,
            return_value=sentinel,
        ) as super_geocode,
    ):
        out = asyncio.run(place.geocode(openai_api_key="sk-test"))
    assert out is sentinel
    super_geocode.assert_awaited_once()


def test_create_model_place_always_addressable_with_components_address() -> None:
    from agate_nodes.geocode_agent.nodes.geocode import _create_model

    state = {
        "original_text": "Visitors at River East Plaza.",
        "geocode_hints": None,
        "extra_fields": {},
    }
    components = {
        "place": {"name": "River East Plaza", "natural": True, "addressable": False},
        "address": "401 E Illinois St",
        "city": "Chicago",
        "state": {"name": "Illinois", "abbr": "IL"},
    }
    model = _create_model("place", "River East Plaza, Chicago, IL", components, state)
    assert isinstance(model, Place)
    assert model._input_addressability is True
    assert model.street_address == "401 E Illinois St"
    assert model.name == "River East Plaza"


def test_place_web_search_fallback_after_inconclusive_pelias() -> None:
    """allow_web_search=False skips upfront search but still falls back after Pelias miss."""
    from agate_utils.geocoding.geocoding_types import (
        GeocodingResult,
        GeocodingResultData,
        GeometryPoint,
    )

    place = Place(
        name="Cafe",
        city="St Paul",
        state_abbr="MN",
        country="US",
        street_address="100 Main St",
    )
    place._input_addressability = True
    place._original_text = "Cafe in St Paul"

    decisive = GeocodingResult(
        geocoder="pelias_search",
        input_str="Cafe",
        result=GeocodingResultData(
            id="gid:1",
            processed_str="Cafe, St Paul, MN, USA",
            geometry=GeometryPoint(coordinates=[-93.1, 44.95]),
            confidence={
                "pelias_name": "Cafe",
                "pelias_locality": "St Paul",
                "pelias_region_a": "MN",
                "pelias_country_code": "US",
                "pelias_gid": "gid:1",
            },
        ),
    )

    async def run() -> GeocodingResult | None:
        async def fake_web(**_kwargs: object) -> bool:
            place._web_search_used = True
            place._web_search_fallback_used = True
            return True

        with (
            patch.object(place, "_geocode_pelias_decisive", side_effect=[None, decisive]) as pelias,
            patch.object(
                place,
                "_try_web_search_address_discovery",
                side_effect=fake_web,
            ) as web,
            patch(
                "agate_nodes.geocode_agent.models.point.place.has_llm_auth",
                return_value=True,
            ),
        ):
            out = await place.geocode(
                pelias_api_key="k",
                openai_api_key="sk",
                brave_search_api_key="brave",
                allow_web_search=False,
            )
            assert place._web_search_fallback_used is True
            web.assert_called_once()
            assert pelias.call_count == 2
            return out

    assert asyncio.run(run()) is decisive
