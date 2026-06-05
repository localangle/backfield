"""PlaceExtract taxonomy includes ``political_district`` (mitigations 2)."""

from __future__ import annotations

from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES


def test_political_district_is_registered_place_extract_type() -> None:
    assert "political_district" in PLACE_EXTRACT_LOCATION_TYPES
