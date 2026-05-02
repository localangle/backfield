"""Tests for geocode ``location`` display refinements and heuristic fallback."""

from agate_nodes.geocode_agent.nodes.emit_location_line import (
    _CONTEXT_SNIPPET_MAX,
    _HINTS_SNIPPET_MAX,
    _heuristic_emit_location,
    _story_context_snippets,
    apply_title_case_location_line,
    refine_location_display_line,
)


def test_apply_title_case_region_and_state_abbr() -> None:
    assert apply_title_case_location_line("central illinois, il") == "Central Illinois, IL"


def test_apply_title_case_neighborhood_city_state() -> None:
    assert (
        apply_title_case_location_line("chicago lawn, chicago, il")
        == "Chicago Lawn, Chicago, IL"
    )


def test_refine_canadian_province_abbr() -> None:
    assert refine_location_display_line("winnipeg, mb, canada") == "Winnipeg, MB, Canada"


def test_refine_collapses_repeated_city_before_state() -> None:
    assert refine_location_display_line("Chicago, Chicago, IL") == "Chicago, IL"
    assert refine_location_display_line("manteno, manteno, il") == "Manteno, IL"


def test_refine_drops_standalone_neighborhood_type_segment() -> None:
    assert (
        refine_location_display_line("Lake View, Neighborhood, Chicago, IL")
        == "Lake View, Chicago, IL"
    )
    assert (
        refine_location_display_line("Norwood Park, neighborhood, chicago, il")
        == "Norwood Park, Chicago, IL"
    )


def test_refine_drops_standalone_district_type_segment() -> None:
    assert (
        refine_location_display_line("Logan Square, District, Chicago, IL")
        == "Logan Square, Chicago, IL"
    )


def test_refine_keeps_neighborhood_word_inside_segment() -> None:
    """Only the standalone segment ``Neighborhood`` is removed, not part of a longer name."""
    assert (
        refine_location_display_line("University Neighborhood, Chicago, IL")
        == "University Neighborhood, Chicago, IL"
    )


def test_refine_does_not_collapse_distinct_segments() -> None:
    assert (
        refine_location_display_line("Los Angeles, Los Angeles County, CA")
        == "Los Angeles, Los Angeles County, CA"
    )


def test_refine_lowercase_of_in_title() -> None:
    assert (
        refine_location_display_line("University Of Oklahoma, Norman, OK")
        == "University of Oklahoma, Norman, OK"
    )


def test_refine_lyric_opera_of() -> None:
    assert (
        refine_location_display_line("Lyric Opera Of Chicago, Chicago, IL")
        == "Lyric Opera of Chicago, Chicago, IL"
    )


def test_refine_house_of_hope() -> None:
    out = refine_location_display_line("House Of Hope, Chicago, IL")
    assert out == "House of Hope, Chicago, IL"


def test_refine_ohare_apostrophe() -> None:
    assert (
        refine_location_display_line("o'hare international airport, chicago, il")
        == "O'Hare International Airport, Chicago, IL"
    )


def test_refine_dotted_initialisms_us_dc() -> None:
    assert (
        refine_location_display_line(
            "U.s. Senate Judiciary Committee Hearing, Washington, DC"
        )
        == "U.S. Senate Judiciary Committee Hearing, Washington, DC"
    )


def test_refine_dotted_initialism_bb() -> None:
    out = refine_location_display_line("B.b. King Hall, Memphis, TN")
    assert out == "B.B. King Hall, Memphis, TN"


def test_refine_phd_style_abbrev() -> None:
    out = refine_location_display_line("ph.d. reception hall, boston, ma")
    assert out == "Ph.D. Reception Hall, Boston, MA"


def test_refine_ampersand_acronym() -> None:
    out = refine_location_display_line("At&t plaza, dallas, tx")
    assert out == "AT&T Plaza, Dallas, TX"


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


def test_story_context_snippets_empty() -> None:
    assert _story_context_snippets({}) == ("(none)", "(none)")


def test_story_context_snippets_truncates_original_text() -> None:
    long = "x" * (_CONTEXT_SNIPPET_MAX + 50)
    orig, hints = _story_context_snippets({"original_text": long})
    assert orig == "x" * _CONTEXT_SNIPPET_MAX + "…"
    assert hints == "(none)"


def test_story_context_snippets_truncates_geocode_hints() -> None:
    long = "y" * (_HINTS_SNIPPET_MAX + 10)
    orig, hints = _story_context_snippets({"geocode_hints": long})
    assert orig == "(none)"
    assert hints == "y" * _HINTS_SNIPPET_MAX + "…"
