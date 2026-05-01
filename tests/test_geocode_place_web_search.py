"""Tests for Place web search gating (Brave then DuckDuckGo)."""

from __future__ import annotations

from unittest.mock import patch

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
