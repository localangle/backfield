"""Consolidate QA: city-level geocoder fallbacks for neighborhood, address, and place."""

from __future__ import annotations

from agate_nodes.geocode_agent.nodes.consolidate import (
    _geocode_city_level_fallback_qa,
    _point_entry_without_geometry,
)
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
)


def _gr(
    *,
    geocoder: str,
    label: str,
    confidence: dict,
    result_id: str = "x",
) -> GeocodingResult:
    return GeocodingResult(
        geocoder=geocoder,
        input_str="q",
        result=GeocodingResultData(
            id=result_id,
            processed_str=label,
            geometry=GeometryPoint(type="Point", coordinates=[-87.6, 41.9]),
            confidence=confidence,
        ),
    )


def test_neighborhood_flags_pelias_locality_when_name_missing_from_label() -> None:
    gr = _gr(
        geocoder="pelias_structured",
        label="Chicago, IL, USA",
        confidence={"pelias_layer": "locality"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "neighborhood",
            "Chicago, IL, USA",
            {"neighborhood": "Norwood Park", "city": "Chicago"},
            gr,
            location_text="",
        )
        is True
    )


def test_neighborhood_ok_when_name_in_label() -> None:
    gr = _gr(
        geocoder="pelias_structured",
        label="Norwood Park, Chicago, IL, USA",
        confidence={"pelias_layer": "locality"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "neighborhood",
            "Norwood Park, Chicago, IL, USA",
            {"neighborhood": "Norwood Park"},
            gr,
        )
        is False
    )


def test_neighborhood_ok_pelias_neighbourhood_layer() -> None:
    gr = _gr(
        geocoder="pelias_structured",
        label="Norwood Park, Chicago, IL, USA",
        confidence={"pelias_layer": "neighbourhood"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "neighborhood",
            gr.result.processed_str,
            {"neighborhood": "Norwood Park"},
            gr,
        )
        is False
    )


def test_address_flags_pelias_locality_with_numbered_street() -> None:
    gr = _gr(
        geocoder="pelias_structured",
        label="Chicago, IL, USA",
        confidence={"pelias_layer": "locality"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "address",
            "Chicago, IL, USA",
            {"address": "100 N Main St", "city": "Chicago"},
            gr,
        )
        is True
    )


def test_address_ok_when_street_prefix_in_label() -> None:
    gr = _gr(
        geocoder="pelias_structured",
        label="100 N Main St, Chicago, IL, USA",
        confidence={"pelias_layer": "address"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "address",
            "100 N Main St, Chicago, IL, USA",
            {"address": "100 N Main St"},
            gr,
        )
        is False
    )


def test_place_flags_locality_when_venue_name_absent() -> None:
    gr = _gr(
        geocoder="pelias_search",
        label="Chicago, IL, USA",
        confidence={"pelias_layer": "locality"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "place",
            "Chicago, IL, USA",
            {"place": {"name": "Wrigley Field"}, "city": "Chicago"},
            gr,
        )
        is True
    )


def test_place_ok_venue_layer() -> None:
    gr = _gr(
        geocoder="pelias_search",
        label="Wrigley Field, Chicago, IL, USA",
        confidence={"pelias_layer": "venue"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "place",
            "Wrigley Field, Chicago, IL, USA",
            {"place": {"name": "Wrigley Field"}},
            gr,
        )
        is False
    )


def test_skips_stylebook_canonical_hits() -> None:
    gr = _gr(
        geocoder="stylebook",
        label="Chicago, IL, USA",
        confidence={"canonical_id": "abc", "source": "canonical"},
        result_id="stylebook:abc",
    )
    assert (
        _geocode_city_level_fallback_qa(
            "neighborhood",
            "Chicago, IL, USA",
            {"neighborhood": "Norwood Park"},
            gr,
        )
        is False
    )


def test_geocodio_city_accuracy_for_neighborhood() -> None:
    gr = _gr(
        geocoder="geocodio_search",
        label="Chicago, IL, USA",
        confidence={"accuracy_type": "City"},
    )
    assert (
        _geocode_city_level_fallback_qa(
            "neighborhood",
            "Chicago, IL, USA",
            {"neighborhood": "Hyde Park"},
            gr,
        )
        is True
    )


def test_rejected_geocode_identity_is_audit_only() -> None:
    rejected = _point_entry_without_geometry(
        {
            "id": "provider:feature",
            "type": "address",
            "location": "1400 Example Avenue, Metro",
            "original_text": "1400 Example Avenue",
            "geocode": {
                "geocode_type": "provider",
                "result": {
                    "id": "provider:feature",
                    "formatted_address": "1400 Example Avenue, Elsewhere",
                    "geometry": {"type": "Point", "coordinates": [-118.0, 34.0]},
                },
            },
        }
    )

    assert rejected["id"].startswith("rejected:")
    assert rejected["geocoded"] is False
    assert rejected["geocode_disposition"] == "rejected"
    assert "geocode" not in rejected
    assert rejected["rejected_geocode_audit"] == {
        "geocode_type": "provider",
        "provider_id": "provider:feature",
        "formatted_address": "1400 Example Avenue, Elsewhere",
    }
