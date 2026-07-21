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


def test_place_geocode_uses_explicit_street_before_web_search() -> None:
    place = Place(name="Garfield Park Conservatory", city="Chicago", state_abbr="IL", country="US")
    place._explicit_street_address = "300 N Central Park Ave"
    place._input_addressability = True
    sentinel = object()
    with (
        patch(
            "agate_nodes.geocode_agent.models.point.place.has_llm_auth",
            return_value=True,
        ),
        patch.object(place, "_search_for_address") as search,
        patch(
            "agate_nodes.geocode_agent.models.point.address.Address.geocode",
            new_callable=AsyncMock,
            return_value=sentinel,
        ) as super_geocode,
    ):
        out = asyncio.run(
            place.geocode(openai_api_key="sk-test", brave_search_api_key="brave")
        )
    assert out is sentinel
    search.assert_not_called()
    super_geocode.assert_awaited_once()
    prep = place._prep()
    assert prep["pelias_structured"]["address"] == "300 N Central Park Ave"
    assert prep["pelias_structured"]["locality"] == "Chicago"


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
    assert model._explicit_street_address == "401 E Illinois St"
    assert model.name == "River East Plaza"