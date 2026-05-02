"""Heuristic tests for geocode ``location`` display fallback (no LLM)."""

from agate_nodes.geocode_agent.nodes.emit_location_line import _heuristic_emit_location


def test_heuristic_strips_trailing_us_for_domestic() -> None:
    assert (
        _heuristic_emit_location("city", "Chicago, IL, US", "Chicago, IL, USA")
        == "Chicago, IL"
    )


def test_heuristic_keeps_country_suffix_for_region_country() -> None:
    out = _heuristic_emit_location("region_country", "Western Europe, USA", "")
    assert "US" in out
    assert "USA" not in out


def test_heuristic_capitalizes_first_letter() -> None:
    assert _heuristic_emit_location("city", "the South, TX", "") == "The South, TX"
