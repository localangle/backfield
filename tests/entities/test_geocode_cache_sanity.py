"""Tests for geocode cache content sanity gates."""

from __future__ import annotations

from backfield_entities.ingest.geocode_cache.sanity import cache_hit_sane_for_substrate


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


def test_place_blocks_neighborhood_canonical_without_poi_name() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="DanDance Art Academy, Chicago, IL",
            components={
                "place": {"name": "DanDance Art Academy"},
                "neighborhood": "Bridgeport",
                "city": "Chicago",
            },
            match_label="Bridgeport, Chicago, IL",
            match_formatted_address="Bridgeport, Chicago, IL",
            match_location_type="neighborhood",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_place_blocks_park_canonical_when_venue_inside_park() -> None:
    """A named venue inside a park must not link to the park canonical."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Tafari's Kitchen, Jackson Park, Chicago, IL",
            components={
                "place": {"name": "Tafari's Kitchen", "addressable": True},
                "city": "Chicago",
            },
            match_label="Jackson Park, Chicago, IL",
            match_formatted_address="Jackson Park, Chicago, IL",
            match_location_type="place",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_place_blocks_place_canonical_when_label_is_only_neighborhood_name() -> None:
    """POI rows must not cache-hit a place canonical named like a neighborhood."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="DanDance Art Academy, Chicago, IL",
            components={"place": {"name": "DanDance Art Academy"}, "city": "Chicago"},
            match_label="Bridgeport, Chicago, IL",
            match_formatted_address="Bridgeport, Chicago, IL",
            match_location_type="place",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_address_blocks_place_canonical_on_neighborhood_token_only() -> None:
    """Street addresses must not cache-hit POI canonicals on embedded neighborhood names."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="address",
            location_text="5400 W. West End Ave., Austin, Chicago, IL",
            components={"address": "5400 W. West End Ave.", "city": "Chicago"},
            match_label="Austin, Chicago, IL",
            match_formatted_address="Austin, Chicago, IL",
            match_location_type="place",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_address_allows_place_canonical_when_poi_name_matches() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="address",
            location_text="XOCO, Chicago, IL",
            components={"place": {"name": "XOCO"}, "address": "XOCO", "city": "Chicago"},
            match_label="XOCO",
            match_formatted_address="XOCO, Chicago, IL",
            match_location_type="place",
            match_geometry_type="Point",
        )
        is True
    )


def test_intersection_blocks_place_canonical_without_street_in_label() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="Illinois St. and Clark St., Chicago, IL",
            components={"city": "Chicago"},
            match_label="Chicago, IL",
            match_formatted_address="Chicago, IL",
            match_location_type="place",
            match_geometry_type="Point",
        )
        is False
    )


def test_intersection_blocks_neighborhood_canonical_without_street_in_label() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="Illinois St. and Clark St., Chicago, IL",
            components={"city": "Chicago"},
            match_label="Bridgeport, Chicago, IL",
            match_formatted_address="Bridgeport, Chicago, IL",
            match_location_type="neighborhood",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_intersection_allows_label_with_street_fragment() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="Illinois St. and Clark St., Chicago, IL",
            components={"city": "Chicago"},
            match_label="Illinois St & Clark St, Chicago, IL",
            match_formatted_address="N Clark St and W Illinois St, Chicago, IL",
            match_location_type="intersection_road",
            match_geometry_type="Point",
        )
        is True
    )
