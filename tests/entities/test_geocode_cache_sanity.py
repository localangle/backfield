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


def test_intersection_blocks_unrelated_street_road_canonical() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="111th Street and Wentworth Avenue, Roseland, Chicago, IL",
            components={"city": "Chicago"},
            match_label="Chicago Avenue, Near North Side, Chicago, IL",
            match_formatted_address="Chicago Avenue, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is False
    )


def test_intersection_blocks_street_road_canonical_even_when_arm_matches() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="Chicago Avenue and Western Avenue, Chicago, IL",
            components={"city": "Chicago"},
            match_label="Chicago Avenue, Near North Side, Chicago, IL",
            match_formatted_address="Chicago Avenue, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is False
    )


def test_intersection_blocks_mismatched_intersection_canonical() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="intersection_road",
            location_text="Belmont Avenue and Clark Street, Lake View, Chicago, IL",
            components={"city": "Chicago"},
            match_label="Illinois St & Clark St, Chicago, IL",
            match_formatted_address="N Clark St and W Illinois St, Chicago, IL",
            match_location_type="intersection_road",
            match_geometry_type="Point",
        )
        is False
    )


def test_street_blocks_different_numbered_street() -> None:
    """A numbered street must not link to a different numbered-street canonical."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="street_road",
            location_text="111th Street, Chicago, IL",
            components={"city": "Chicago"},
            match_label="62nd Street, Chicago, IL",
            match_formatted_address="62nd Street, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is False
    )


def test_street_blocks_avenue_sharing_only_city_and_state() -> None:
    """A different avenue must not link to a self-named street canonical (Chicago Avenue)."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="street_road",
            location_text="Archer Avenue, Chicago, IL",
            components={"city": "Chicago"},
            match_label="Chicago Avenue, Near North Side, Chicago, IL",
            match_formatted_address="Chicago Avenue, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is False
    )


def test_street_blocks_numeric_near_miss() -> None:
    """``62nd`` must not be treated as a substring match of ``162nd``."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="street_road",
            location_text="162nd Street, Chicago, IL",
            components={"city": "Chicago"},
            match_label="62nd Street, Chicago, IL",
            match_formatted_address="62nd Street, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is False
    )


def test_street_allows_same_street() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="street_road",
            location_text="62nd Street, Chicago, IL",
            components={"city": "Chicago"},
            match_label="62nd Street, Chicago, IL",
            match_formatted_address="62nd Street, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is True
    )


def test_street_allows_same_street_with_different_neighborhood_tail() -> None:
    """Same street annotated with different neighborhoods still links (tail is ignored)."""
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="street_road",
            location_text="Chicago Avenue, Downtown Chicago, Chicago, IL",
            components={"city": "Chicago"},
            match_label="Chicago Avenue, Near North Side, Chicago, IL",
            match_formatted_address="Chicago Avenue, Chicago, IL",
            match_location_type="street_road",
            match_geometry_type="LineString",
        )
        is True
    )


def test_place_blocks_address_canonical_without_venue_name() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Gene's Bistro, Chicago, IL",
            components={"place": {"name": "Gene's Bistro"}, "city": "Chicago"},
            match_label="500 N Franklin St, Chicago, IL",
            match_formatted_address="500 N Franklin St, Chicago, IL",
            match_location_type="address",
            match_geometry_type="Point",
        )
        is False
    )


def test_place_allows_address_canonical_when_venue_name_present() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Gene's Bistro, Chicago, IL",
            components={"place": {"name": "Gene's Bistro"}, "city": "Chicago"},
            match_label="Gene's Bistro, Chicago, IL",
            match_formatted_address="Gene's Bistro, Chicago, IL",
            match_location_type="address",
            match_geometry_type="Point",
        )
        is True
    )


def test_place_blocks_region_state_when_poi_name_absent() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Kingdom Home, Eastern Uganda, Uganda",
            components={"place": {"name": "Kingdom Home"}},
            match_label="Eastern Uganda",
            match_formatted_address="Eastern Uganda",
            match_location_type="region_state",
            match_geometry_type="Polygon",
        )
        is False
    )


def test_place_token_fallback_uses_location_text_when_components_empty() -> None:
    assert (
        cache_hit_sane_for_substrate(
            substrate_location_type="place",
            location_text="Kingdom Home, Eastern Uganda, Uganda",
            components={},
            match_label="Eastern Uganda",
            match_formatted_address="Eastern Uganda",
            match_location_type="region_state",
            match_geometry_type="Polygon",
        )
        is False
    )
