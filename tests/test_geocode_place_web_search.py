"""Tests for the Place address-search provider waterfall."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from agate_nodes.geocode_agent.models.point.place import ExtractedAddress, Place
from agate_utils.search import SearchResponse, SearchResult


def _sample_results(query: str) -> SearchResponse:
    return SearchResponse(
        success=True,
        results=[
            SearchResult(title="t", snippet="s", url="https://example.com"),
        ],
        query=query,
    )


def test_place_search_ddg_when_no_brave_key() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    complete = ExtractedAddress(
        address_found=True,
        street="100 Main St",
        city="St Paul",
        state="MN",
        country="US",
        evidence_indexes=[0],
    )
    with (
        patch.object(place, "_generate_search_query", return_value="Cafe St Paul address"),
        patch("agate_nodes.geocode_agent.models.point.place.brave_web_search") as web,
        patch("agate_nodes.geocode_agent.models.point.place.brave_place_search") as brave,
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=_sample_results("Cafe St Paul address"),
        ) as ddg,
        patch.object(place, "_extract_and_parse_address", return_value=complete),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key=None,
                openai_api_key="sk",
                is_fallback=False,
            )
        )
    web.assert_not_called()
    brave.assert_not_called()
    ddg.assert_called_once()
    assert out is True
    assert place._address_source == "duckduckgo"


def test_place_search_brave_web_complete_skips_fallbacks() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    complete = ExtractedAddress(
        address_found=True,
        street="100 Main St",
        city="St Paul",
        state="MN",
        country="US",
        evidence_indexes=[0],
    )
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_web_search",
            return_value=_sample_results("q1"),
        ) as web,
        patch("agate_nodes.geocode_agent.models.point.place.brave_place_search") as place_search,
        patch("agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo") as ddg,
        patch.object(place, "_extract_and_parse_address", return_value=complete),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key="k",
                openai_api_key="sk",
                is_fallback=False,
            )
        )
    web.assert_called_once()
    place_search.assert_not_called()
    ddg.assert_not_called()
    assert out is True
    assert place._address_source == "brave_web"
    assert place._prep()["pelias_structured"]["address"] == "100 Main St"


def test_place_search_web_unusable_then_place_complete() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    complete = ExtractedAddress(
        address_found=True,
        street="100 Main St",
        city="St Paul",
        state="MN",
        country="US",
        evidence_indexes=[0],
    )
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_web_search",
            return_value=_sample_results("q1"),
        ) as web,
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=_sample_results("q1"),
        ) as place_search,
        patch("agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo") as ddg,
        patch.object(place, "_extract_and_parse_address", side_effect=[None, complete]),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key="k",
                openai_api_key="sk",
                is_fallback=False,
            )
        )
    web.assert_called_once()
    place_search.assert_called_once()
    ddg.assert_not_called()
    assert out is True
    assert place._address_source == "brave_place"
    assert [row["outcome"] for row in place._address_search_attempts] == [
        "no_usable_address",
        "complete_address",
    ]


def test_place_search_place_unusable_then_ddg_complete() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    complete = ExtractedAddress(
        address_found=True,
        street="100 Main St",
        city="St Paul",
        state="MN",
        country="US",
    )
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_web_search",
            return_value=SearchResponse(success=True, results=[], query="q1"),
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=_sample_results("q1"),
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=_sample_results("q1"),
        ) as ddg,
        patch.object(place, "_extract_and_parse_address", side_effect=[None, complete]),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key="k",
                openai_api_key="sk",
                is_fallback=False,
            )
        )
    ddg.assert_called_once()
    assert out is True
    assert place._address_source == "duckduckgo"


def test_place_search_all_providers_unusable() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    response = _sample_results("q1")
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_web_search",
            return_value=response,
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=response,
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=response,
        ),
        patch.object(place, "_extract_and_parse_address", return_value=None),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key="k",
                openai_api_key="sk",
                is_fallback=False,
            )
        )
    assert out is False
    assert place._address_source is None
    assert [row["provider"] for row in place._address_search_attempts] == [
        "brave_web",
        "brave_place",
        "duckduckgo",
    ]


def test_place_search_provider_errors_continue_waterfall() -> None:
    place = Place(name="Cafe", city="St Paul", state_abbr="MN", country="US")
    complete = ExtractedAddress(
        address_found=True,
        street="100 Main St",
        city="St Paul",
        state="MN",
        country="US",
    )
    with (
        patch.object(place, "_generate_search_query", return_value="q1"),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_web_search",
            side_effect=RuntimeError("web unavailable"),
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.brave_place_search",
            return_value=SearchResponse(
                success=False,
                results=[],
                query="q1",
                error="place unavailable",
            ),
        ),
        patch(
            "agate_nodes.geocode_agent.models.point.place.search_web_duckduckgo",
            return_value=_sample_results("q1"),
        ),
        patch.object(place, "_extract_and_parse_address", return_value=complete),
    ):
        out = asyncio.run(
            place._try_web_search_address_discovery(
                brave_search_api_key="k",
                openai_api_key="sk",
                is_fallback=False,
            )
        )

    assert out is True
    assert place._address_source == "duckduckgo"
    assert [row["outcome"] for row in place._address_search_attempts] == [
        "error",
        "error",
        "complete_address",
    ]


def test_us_building_address_rejects_street_without_house_number() -> None:
    place = Place(name="Oakland Station", city="Oakland", state_abbr="CA", country="US")
    partial = ExtractedAddress(
        address_found=True,
        street="105th Ave",
        city="Oakland",
        state="CA",
        country="US",
    )
    assert place._complete_extracted_address(partial, result_count=1) is None


def test_oakland_station_web_evidence_extracts_complete_address() -> None:
    place = Place(name="Oakland Station", city="Oakland", state_abbr="CA", country="US")
    place._original_text = "Ruiz lives at the Oakland Station building on 105th Avenue."
    place._geocode_hints = "Formerly called Oakland Station Senior."
    response = SearchResponse(
        success=True,
        query="Oakland Station 105th Avenue Oakland CA address",
        results=[
            SearchResult(
                title="Oakland Station - 1428 105th Ave Oakland, CA 94603",
                snippet="Oakland Station is located at 1428 105th Ave in Oakland, CA.",
                url="https://www.apartments.com/oakland-station/",
            ),
            SearchResult(
                title="Contact Us - Oakland Station",
                snippet="1428 105th Avenue Oakland, CA 94603",
                url="https://www.oaklandstationapts.com/contact_us/",
            ),
        ],
    )
    llm_response = (
        '{"address_found":true,"street":"1428 105th Avenue","city":"Oakland",'
        '"state":"CA","zipcode":"94603","country":"US","evidence_indexes":[0,1]}'
    )
    with patch(
        "agate_nodes.geocode_agent.models.point.place.call_llm",
        return_value=llm_response,
    ):
        extracted = place._extract_and_parse_address(response.query, response, "sk")

    assert extracted is not None
    assert extracted.street == "1428 105th Avenue"
    assert extracted.zipcode == "94603"
    assert extracted.evidence_indexes == [0, 1]


def test_conflicting_web_evidence_remains_unresolved() -> None:
    place = Place(name="Station", city="Oakland", state_abbr="CA", country="US")
    response = _sample_results("Station Oakland address")
    with patch(
        "agate_nodes.geocode_agent.models.point.place.call_llm",
        return_value='{"address_found":false,"evidence_indexes":[]}',
    ):
        extracted = place._extract_and_parse_address(response.query, response, "sk")

    assert extracted is None


def test_external_geocode_merges_sanitized_search_audit() -> None:
    from agate_nodes.geocode_agent.nodes.geocode import orchestrate_external_geocode

    place = Place(name="Oakland Station", city="Oakland", state_abbr="CA", country="US")
    place._address_search_attempts = [
        {
            "provider": "brave_web",
            "result_count": 10,
            "outcome": "complete_address",
        }
    ]
    place._address_source = "brave_web"
    place._web_search_fallback_used = True
    state = {
        "location_type": "place",
        "location_text": "Oakland Station, Oakland, CA",
        "location_components": {},
        "router_audit": {"strategy_selected": "web_search"},
    }
    with (
        patch(
            "agate_nodes.geocode_agent.nodes.geocode._create_model",
            return_value=place,
        ),
        patch.object(Place, "geocode", new_callable=AsyncMock, return_value=None),
    ):
        result = asyncio.run(orchestrate_external_geocode(state))  # type: ignore[arg-type]

    audit = result["router_audit"]
    assert audit["strategy_selected"] == "web_search"
    assert audit["address_source"] == "brave_web"
    assert audit["web_search_fallback_used"] is True
    assert audit["search_attempts"] == place._address_search_attempts
    assert "query" not in audit["search_attempts"][0]


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
