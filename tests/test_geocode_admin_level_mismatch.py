"""Consolidate QA: city + PlaceExtract city rejects state-only geocoder hits."""

from __future__ import annotations

from agate_nodes.geocode_agent.nodes.consolidate import _city_geocode_admin_level_mismatch
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
)


def _result(
    *,
    geocoder: str,
    label: str,
    confidence: dict,
) -> GeocodingResult:
    return GeocodingResult(
        geocoder=geocoder,
        input_str="q",
        result=GeocodingResultData(
            id="x",
            processed_str=label,
            geometry=GeometryPoint(type="Point", coordinates=[-69.7, 44.2]),
            confidence=confidence,
        ),
    )


def test_city_mismatch_when_pelias_region_and_city_not_in_label() -> None:
    gr = _result(
        geocoder="pelias_structured",
        label="Maine, United States",
        confidence={"pelias_layer": "region"},
    )
    assert (
        _city_geocode_admin_level_mismatch(
            "city",
            "Maine, United States",
            {"city": "Portland"},
            gr,
        )
        is True
    )


def test_city_ok_when_city_token_in_label() -> None:
    gr = _result(
        geocoder="pelias_structured",
        label="Portland, ME, USA",
        confidence={"pelias_layer": "locality"},
    )
    assert (
        _city_geocode_admin_level_mismatch(
            "city",
            "Portland, ME, USA",
            {"city": "Portland"},
            gr,
        )
        is False
    )


def test_city_mismatch_nominatim_state_type() -> None:
    gr = _result(
        geocoder="nominatim",
        label="Maine, United States",
        confidence={"nominatim_type": "state"},
    )
    assert (
        _city_geocode_admin_level_mismatch(
            "city",
            "Maine, United States",
            {"city": "Portland"},
            gr,
        )
        is True
    )


def test_city_mismatch_geocodio_state_accuracy() -> None:
    gr = _result(
        geocoder="geocodio_search",
        label="Maine, USA",
        confidence={"accuracy_type": "State"},
    )
    assert (
        _city_geocode_admin_level_mismatch(
            "city",
            "Maine, USA",
            {"city": "Portland"},
            gr,
        )
        is True
    )


def test_skips_when_no_city_in_components() -> None:
    gr = _result(
        geocoder="pelias_structured",
        label="Maine, United States",
        confidence={"pelias_layer": "region"},
    )
    assert _city_geocode_admin_level_mismatch("city", "Maine, United States", {}, gr) is False
