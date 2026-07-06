"""Tests for compact PlaceExtract enum code maps."""

from agate_nodes.place_extract.compact_codes import (
    NATURE_FROM_CODE,
    NATURE_TO_CODE,
    expand_address_place_kind,
    expand_location_type,
    expand_nature,
)
from backfield_entities.entities.location.types import PLACE_MENTION_NATURE_VALUES


def test_nature_codes_cover_all_values() -> None:
    assert set(NATURE_TO_CODE.keys()) == set(PLACE_MENTION_NATURE_VALUES)
    assert len(NATURE_FROM_CODE) == len(NATURE_TO_CODE)
    assert set(NATURE_FROM_CODE.values()) == set(NATURE_TO_CODE.keys())


def test_expand_location_type_round_trips_codes() -> None:
    assert expand_location_type("ih") == "intersection_highway"
    assert expand_location_type("ci") == "city"


def test_expand_location_type_accepts_full_name() -> None:
    assert expand_location_type("intersection_highway") == "intersection_highway"


def test_expand_location_type_unknown_passes_through() -> None:
    assert expand_location_type("custom_type") == "custom_type"


def test_expand_nature_round_trips_codes() -> None:
    assert expand_nature("p") == "primary"
    assert expand_nature("c") == "context"
    assert expand_nature("h") == "historical"


def test_expand_nature_unknown_maps_to_unknown() -> None:
    assert expand_nature("bogus") == "unknown"
    assert expand_nature("") == "unknown"


def test_expand_address_place_kind_round_trips() -> None:
    assert expand_address_place_kind("pv") == "private_residence"
    assert expand_address_place_kind("public_named") == "public_named"


def test_expand_address_place_kind_empty_stays_empty() -> None:
    assert expand_address_place_kind("") == ""
