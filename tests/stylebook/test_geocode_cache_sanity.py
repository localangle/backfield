"""Tests for geocode cache content sanity gates."""

from __future__ import annotations

from backfield_stylebook.geocode_cache_sanity import cache_hit_sane_for_substrate


def test_address_blocks_city_canonical_without_street_in_label() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="address",
            location_text="500 N. Franklin St., Chicago, IL",
            components={"address": "500 N. Franklin St.", "city": "Chicago"},
            match_label="Chicago, IL",
            match_formatted_address="Chicago, IL",
            match_location_type="city",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_address_allows_label_with_street_fragment() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="address",
            location_text="500 N. Franklin St., Chicago, IL",
            components={"address": "500 N. Franklin St.", "city": "Chicago"},
            match_label="500 N Franklin St, Chicago, IL",
            match_formatted_address="500 N Franklin St, Chicago, IL 60610",
            match_location_type="address",
            match_geometry_type="Point",
        )
        is True
    )


def test_place_blocks_city_canonical_without_venue_name() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Gene's Bistro, Midway International Airport, Chicago, IL",
            components={
                "place": {"name": "Gene's Bistro", "addressable": True},
                "city": "Chicago",
            },
            match_label="Chicago, IL",
            match_formatted_address="Chicago, IL",
            match_location_type="city",
            match_geometry_type="Polygon",
        )
        is False
    )
