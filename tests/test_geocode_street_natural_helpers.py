"""Street-road name matching and natural query helpers."""

from __future__ import annotations

from agate_nodes.geocode_agent.models.area.natural import NaturalPlace
from agate_nodes.geocode_agent.models.area.street_road import (
    StreetRoad,
    street_name_heads_compatible,
)


def test_street_name_heads_keep_directional_suffix_only() -> None:
    assert street_name_heads_compatible("West Boulevard", "West Boulevard North")
    assert street_name_heads_compatible("West Boulevard", "West Boulevard South")
    assert not street_name_heads_compatible("West Boulevard", "West Boulevard Court")
    assert not street_name_heads_compatible("West Boulevard", "West Nifong Boulevard")


def test_street_route_aliases_match_mo_j() -> None:
    assert street_name_heads_compatible("Missouri Route J", "MO-J")
    assert street_name_heads_compatible("Missouri Route J", "Route J")
    assert street_name_heads_compatible("U.S. Route 40", "US-40")
    assert street_name_heads_compatible("Interstate 70", "I-70")
    assert street_name_heads_compatible("Boone County Route BB", "CR-BB")
    assert street_name_heads_compatible("Boone County Route BB", "Route BB")


def test_natural_build_query_is_bare_feature_name() -> None:
    place = NaturalPlace(
        name="Mississippi River, MO",
        place_name="Mississippi River",
        place_is_natural=True,
        state_abbr="MO",
        state="Missouri",
    )
    assert place._build_query() == "Mississippi River"
    assert "Missouri" in place._build_qualified_query() or "MO" in place._build_qualified_query()


def test_natural_filters_candidates_by_state() -> None:
    place = NaturalPlace(
        name="Mississippi River",
        place_name="Mississippi River",
        place_is_natural=True,
        state_abbr="MO",
        state="Missouri",
        country="US",
    )
    candidates = [
        {
            "display_name": "Mississippi River, United States",
            "address": {"state": "Illinois", "ISO3166-2-lvl4": "US-IL", "country_code": "us"},
        },
        {
            "display_name": "Mississippi River, Missouri, United States",
            "address": {"state": "Missouri", "ISO3166-2-lvl4": "US-MO", "country_code": "us"},
        },
        {
            "display_name": "Oahu, Tiamao, Papara, Windward Islands, French Polynesia",
            "address": {"country": "France", "country_code": "pf"},
        },
    ]
    filtered = place._filter_candidates_by_state(candidates)
    assert len(filtered) == 1
    assert filtered[0]["address"]["ISO3166-2-lvl4"] == "US-MO"


def test_natural_rejects_abbr_substring_false_positive() -> None:
    """``state='HI'`` must not match inside 'Hitiaʻa' / French Polynesia."""
    place = NaturalPlace(
        name="Oahu",
        place_name="Oahu",
        place_is_natural=True,
        state_abbr="HI",
        state="HI",
        country="US",
    )
    foreign = {
        "display_name": "Oahu, Papenoo, Hitiaʻa ʻo te Rā, Windward Islands, French Polynesia",
        "address": {"country": "France", "country_code": "pf"},
    }
    assert place._candidate_matches_state(foreign) is False


def test_natural_rejects_wasatch_county_street_false_positive() -> None:
    place = NaturalPlace(
        name="Wasatch Mountains",
        place_name="Wasatch Mountains",
        place_is_natural=True,
        state_abbr="UT",
        state="Utah",
        country="US",
    )
    street = {
        "display_name": (
            "Mountains West, 2211, West 3000 South, Charleston, "
            "Wasatch County, Utah, 84049, United States"
        ),
        "address": {"state": "Utah", "ISO3166-2-lvl4": "US-UT", "country_code": "us"},
    }
    assert place._filter_candidates_by_state([street]) == []


def test_natural_country_filter_rejects_canada_when_us() -> None:
    place = NaturalPlace(
        name="Mississippi River",
        place_name="Mississippi River",
        place_is_natural=True,
        country="US",
    )
    canada = {
        "display_name": "Mississippi River, Dalhousie Lake, Ontario, Canada",
        "address": {"country": "Canada", "country_code": "ca"},
    }
    assert place._candidate_matches_state(canada) is False


def test_street_road_city_gate_skips_when_city_equals_street_name() -> None:
    road = StreetRoad(name="Missouri Route J", city="Missouri Route J", state="MO")
    assert road._city_agrees({"pelias_locality": "Columbia", "pelias_county": "Boone"})
