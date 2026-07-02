"""Tests for compact PlaceExtract enum code maps."""

from agate_nodes.place_extract.compact_codes import (
    expand_address_place_kind,
    expand_location_type,
    expand_nature,
)


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


def test_expand_nature_unknown_maps_to_unknown() -> None:
    assert expand_nature("bogus") == "unknown"
    assert expand_nature("") == "unknown"


def test_expand_address_place_kind_round_trips() -> None:
    assert expand_address_place_kind("pv") == "private_residence"
    assert expand_address_place_kind("public_named") == "public_named"


def test_expand_address_place_kind_empty_stays_empty() -> None:
    assert expand_address_place_kind("") == ""
