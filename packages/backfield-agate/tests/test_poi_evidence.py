"""Synthetic regression tests for Pelias POI evidence and consolidate exception."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from agate_nodes.geocode_agent.models.point.place import Place
from agate_nodes.geocode_agent.nodes.consolidate import consolidate_node
from agate_nodes.geocode_agent.poi_evidence import (
    has_exact_address_evidence,
    has_poi_identity_evidence,
    is_decisive_pelias_candidate,
    pelias_poi_result_acceptable,
    select_uniquely_decisive_candidate,
)
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
)


def _pelias_result(
    *,
    label: str,
    name: str | None = None,
    housenumber: str | None = None,
    street: str | None = None,
    locality: str | None = "Chicago",
    region_a: str | None = "IL",
    country_code: str | None = "US",
    gid: str = "openstreetmap:venue:1",
    lon: float = -87.65,
    lat: float = 41.95,
    geocoder: str = "pelias_search",
) -> GeocodingResult:
    confidence: dict = {
        "pelias_name": name,
        "pelias_housenumber": housenumber,
        "pelias_street": street,
        "pelias_locality": locality,
        "pelias_region_a": region_a,
        "pelias_country_code": country_code,
        "pelias_gid": gid,
        "pelias_layer": "venue",
    }
    return GeocodingResult(
        geocoder=geocoder,
        input_str=label,
        result=GeocodingResultData(
            id=gid,
            processed_str=label,
            geometry=GeometryPoint(coordinates=[lon, lat]),
            confidence=confidence,
        ),
    )


def _venue_components(
    *,
    name: str,
    address: str,
    city: str = "Chicago",
    state_abbr: str = "IL",
) -> dict:
    return {
        "place": {"name": name, "addressable": True},
        "address": address,
        "city": city,
        "state": {"name": "Illinois", "abbr": state_abbr},
        "country": {"name": "United States", "abbr": "US"},
    }


# --- Labeled set modeled on Sun-Times venues (synthetic Pelias payloads) ---

@pytest.mark.parametrize(
    "name,address,label,pelias_name,expect_accept",
    [
        (
            "Martyrs",
            "3855 N. Lincoln Ave.",
            "Martyrs, North Side, Chicago, IL, USA",
            "Martyrs",
            True,
        ),
        (
            "The Salt Shed",
            "1357 N Elston Ave",
            "Salt Shed, Chicago, IL, USA",
            "Salt Shed",
            True,
        ),
        (
            "Music Box Theatre",
            "3733 N Southport Ave",
            "Music Box Theatre, Chicago, IL, USA",
            "Music Box Theatre",
            True,
        ),
        (
            "Chicago Shakespeare Theater",
            "800 E Grand Ave",
            "Chicago Shakespeare Theater, Chicago, IL, USA",
            "Chicago Shakespeare Theater",
            True,
        ),
        # Wrong venue identity — must reject
        (
            "Urban Theater Company",
            "1000 N Wells St",
            "Lookingglass Theatre Company, Chicago, IL, USA",
            "Lookingglass Theatre Company",
            False,
        ),
        (
            "Drury Lane Theatre",
            "100 Drury Lane",
            "Drury Lane, Missouri, USA",
            "Drury Lane",
            False,
        ),
        (
            "Milwaukee Art Museum",
            "700 N Art Museum Dr",
            "Milwaukee Art Museum, Jacksonville, FL, USA",
            "Milwaukee Art Museum",
            False,
        ),
        # Intentional non-match: Theater vs Theatre spelling
        (
            "Chicago Shakespeare Theater",
            "800 E Grand Ave",
            "Chicago Shakespeare Theatre, Chicago, IL, USA",
            "Chicago Shakespeare Theatre",
            False,
        ),
    ],
)
def test_labeled_venue_outcomes(
    name: str,
    address: str,
    label: str,
    pelias_name: str,
    expect_accept: bool,
) -> None:
    comps = _venue_components(name=name, address=address)
    # Drury Lane wrong state / Milwaukee wrong city need matching jurisdiction fields
    locality = "Chicago"
    region_a = "IL"
    if "Missouri" in label:
        locality = "St Louis"
        region_a = "MO"
        comps["city"] = "Oakbrook Terrace"
        comps["state"] = {"name": "Illinois", "abbr": "IL"}
    if "Jacksonville" in label:
        locality = "Jacksonville"
        region_a = "FL"

    result = _pelias_result(
        label=label,
        name=pelias_name,
        locality=locality,
        region_a=region_a,
        country_code="US",
        gid=f"openstreetmap:venue:{name}",
    )
    assert pelias_poi_result_acceptable(comps, result) is expect_accept


def test_missing_pelias_name_fails_closed() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    result = _pelias_result(
        label="Martyrs, Chicago, IL, USA",
        name=None,
        locality="Chicago",
        region_a="IL",
    )
    assert has_poi_identity_evidence(comps, result) is False
    assert pelias_poi_result_acceptable(comps, result) is False


def test_conflicting_house_number_rejects() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    result = _pelias_result(
        label="2400 N Lincoln Ave, Chicago, IL, USA",
        name="Martyrs",
        housenumber="2400",
        street="N Lincoln Ave",
        locality="Chicago",
        region_a="IL",
    )
    assert is_decisive_pelias_candidate(comps, result) is False


def test_exact_address_evidence_accepts_without_venue_name() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    result = _pelias_result(
        label="3855 N Lincoln Ave, Chicago, IL, USA",
        name=None,
        housenumber="3855",
        street="N Lincoln Ave",
        locality="Chicago",
        region_a="IL",
    )
    assert has_exact_address_evidence(comps, result) is True
    assert pelias_poi_result_acceptable(comps, result) is True
    # Address evidence path is not "unverified"
    from agate_nodes.geocode_agent.poi_evidence import poi_acceptance_is_address_unverified

    assert poi_acceptance_is_address_unverified(comps, result) is False


def test_same_name_different_city_rejects() -> None:
    comps = _venue_components(name="Music Box", address="100 Main St", city="Chicago")
    result = _pelias_result(
        label="Music Box, Evanston, IL, USA",
        name="Music Box",
        locality="Evanston",
        region_a="IL",
    )
    assert pelias_poi_result_acceptable(comps, result) is False


def test_uniquely_decisive_candidate_required() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    a = _pelias_result(
        label="Martyrs, Chicago, IL, USA",
        name="Martyrs",
        gid="openstreetmap:venue:a",
        lon=-87.65,
        lat=41.95,
    )
    b = _pelias_result(
        label="Martyrs, Chicago, IL, USA",
        name="Martyrs",
        gid="openstreetmap:venue:b",
        lon=-87.70,
        lat=41.90,
    )
    assert select_uniquely_decisive_candidate(comps, [a, b]) is None
    assert select_uniquely_decisive_candidate(comps, [a]) is a
    # Same identity (shared gid) is fine
    b_same = _pelias_result(
        label="Martyrs, Chicago, IL, USA",
        name="Martyrs",
        gid="openstreetmap:venue:a",
        lon=-87.65,
        lat=41.95,
    )
    assert select_uniquely_decisive_candidate(comps, [a, b_same]) is a


def test_place_prep_uses_street_address_for_structured_pelias() -> None:
    place = Place(
        name="Martyrs",
        city="Chicago",
        state_abbr="IL",
        country="US",
        street_address="3855 N. Lincoln Ave.",
    )
    prep = place._prep()
    assert prep["pelias_structured"]["address"] == "3855 N. Lincoln Ave."
    assert "Martyrs" in prep["full_address"]
    assert "3855 N. Lincoln Ave." in prep["full_address"]


def test_place_prep_falls_back_to_venue_name_without_street() -> None:
    place = Place(name="Martyrs", city="Chicago", state_abbr="IL", country="US")
    prep = place._prep()
    assert prep["pelias_structured"]["address"] == "Martyrs"


def _place_consolidate_state(
    *,
    components: dict,
    result: GeocodingResult,
) -> dict:
    return {
        "location_type": "place",
        "location_text": place_name_text(components),
        "location_components": components,
        "original_text": "Mention in article",
        "geocode_hints": "",
        "geocoding_result": result,
        "extra_fields": {},
        "advanced_quiet_logs": True,
    }


def place_name_text(components: dict) -> str:
    place = components.get("place") or {}
    name = place.get("name") if isinstance(place, dict) else str(place or "")
    city = components.get("city") or ""
    return f"{name}, {city}" if city else str(name)


def test_consolidate_keeps_poi_identity_match_with_unverified_marker() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    result = _pelias_result(
        label="Martyrs, North Side, Chicago, IL, USA",
        name="Martyrs",
        locality="Chicago",
        region_a="IL",
        gid="openstreetmap:venue:martyrs",
    )
    # Label has no house number → shared gate fails; exception should keep geometry.
    from backfield_entities.ingest.geocode_cache.sanity import (
        explicit_location_components_match_labels,
    )

    assert (
        explicit_location_components_match_labels(
            components=comps,
            location_text="Martyrs, Chicago",
            match_label=result.result.processed_str,
        )
        is False
    )

    state = _place_consolidate_state(components=comps, result=result)

    async def run() -> dict:
        with patch(
            "agate_nodes.geocode_agent.nodes.consolidate.compute_emit_location_line",
            new=AsyncMock(return_value="Martyrs, Chicago, IL"),
        ):
            return await consolidate_node(state)

    output = asyncio.run(run())
    points = output["final_output"]["places"]["points"]
    review = output["final_output"]["places"]["needs_review"]
    assert len(review) == 0
    assert len(points) == 1
    assert points[0]["address_verification"] == "unverified"
    assert points[0]["geocode_qa_code"] == "poi_identity_match"
    assert points[0]["geocode"]["result"]["geometry"]["type"] == "Point"


def test_consolidate_rejects_wrong_venue_identity() -> None:
    comps = _venue_components(name="Urban Theater Company", address="1000 N Wells St")
    result = _pelias_result(
        label="Lookingglass Theatre Company, Chicago, IL, USA",
        name="Lookingglass Theatre Company",
        locality="Chicago",
        region_a="IL",
        gid="openstreetmap:venue:lookingglass",
    )
    state = _place_consolidate_state(components=comps, result=result)

    async def run() -> dict:
        with patch(
            "agate_nodes.geocode_agent.nodes.consolidate.compute_emit_location_line",
            new=AsyncMock(return_value="Lookingglass Theatre Company, Chicago, IL"),
        ):
            return await consolidate_node(state)

    output = asyncio.run(run())
    points = output["final_output"]["places"]["points"]
    review = output["final_output"]["places"]["needs_review"]
    assert len(points) == 0
    assert len(review) == 1
    assert review[0]["geocode_qa_code"] == "geocode_component_mismatch"
    assert "geometry" not in review[0].get("geocode", {}).get("result", {})


def test_non_pelias_geocoder_does_not_get_poi_exception() -> None:
    comps = _venue_components(name="Martyrs", address="3855 N. Lincoln Ave.")
    result = _pelias_result(
        label="Martyrs, Chicago, IL, USA",
        name="Martyrs",
        locality="Chicago",
        region_a="IL",
        geocoder="nominatim",
    )
    assert pelias_poi_result_acceptable(comps, result) is False
