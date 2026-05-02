"""Tests for geocode ``location`` display title-casing and heuristic fallback."""

from agate_nodes.geocode_agent.nodes.emit_location_line import (
    _heuristic_emit_location,
    apply_title_case_location_line,
)


def test_apply_title_case_region_and_state_abbr() -> None:
    assert apply_title_case_location_line("central illinois, il") == "Central Illinois, IL"


def test_apply_title_case_neighborhood_city_state() -> None:
    assert (
        apply_title_case_location_line("chicago lawn, chicago, il")
        == "Chicago Lawn, Chicago, IL"
    )


def test_heuristic_strips_trailing_us_for_domestic() -> None:
    assert (
        _heuristic_emit_location("city", "Chicago, IL, US", "Chicago, IL, USA")
        == "Chicago, IL"
    )


def test_heuristic_keeps_country_suffix_for_region_country() -> None:
    out = _heuristic_emit_location("region_country", "Western Europe, USA", "")
    assert "US" in out
    assert "USA" not in out


def test_heuristic_title_cases_words_and_state_abbr() -> None:
    assert _heuristic_emit_location("city", "the South, TX", "") == "The South, TX"
