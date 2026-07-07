"""Tests for PlaceExtract prompt resolution and placeholder substitution."""

from __future__ import annotations

import re
from pathlib import Path

from agate_nodes.place_extract.prompt_template import (
    normalize_prompt_for_comparison,
    resolve_place_extract_prompt,
    substitute_prompt_placeholders,
)
from agate_utils.prompt_placeholders import extract_json_path

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "packages"
    / "backfield-agate"
    / "src"
    / "agate_nodes"
    / "place_extract"
    / "prompts"
    / "extract.md"
)


def test_place_extract_prompt_excludes_non_location_candidate_patterns() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "## Hard stops — the place test" in prompt
    assert "Person with appended geography" in prompt
    assert "Brandon Johnson, Chicago, IL" in prompt
    assert "Sports team, game, league, division, or era" in prompt
    assert "Bears-Packers game" in prompt
    assert "Game 7" in prompt
    assert "1969 Bears" in prompt
    assert "American Basketball Association" in prompt
    assert "American League Central" in prompt
    assert "Eastern Conference" in prompt
    assert "Athletic conference, class, or bracket" in prompt
    assert "Class 3a, IL" in prompt
    assert "IHSA 4A" in prompt
    assert "West Suburban Conference Silver" in prompt
    assert "Demographic or identity-based area label" in prompt
    assert "Black neighborhoods, Chicago, IL" in prompt
    assert "Broad descriptive macro-area" in prompt
    assert "Forty States, US" in prompt
    assert "International cities" in prompt
    assert "Paris, France" in prompt
    assert "Washington, DC vs Washington state" in prompt
    assert "Street-type spelling" in prompt
    assert "103rd Street, Chicago, IL" in prompt
    assert "NFL Scouting Combine" in prompt
    assert "Venue interior or subpart" in prompt
    assert "concession stand" in prompt
    assert "dugout" in prompt
    assert "Organization with inferred headquarters" in prompt
    assert "American Medical Association, IL" in prompt


def test_place_extract_prompt_includes_historical_nature() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "**historical**" in prompt
    assert "past events, precedent, or historical comparison" in prompt


def test_place_extract_prompt_includes_tournament_scoreline_rules() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "**Venue does not replace schools:**" in prompt
    assert "Title: St. Rita 12, Triad 11" in prompt
    assert "Third place: Naperville Central vs. Mount Carmel, 9" in prompt
    assert "still extract every named school and venue on the same lines" in prompt


def test_place_extract_prompt_normalizes_block_addresses() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "**Block addresses (critical)**" in prompt
    assert "6500 S Hermitage Ave, Chicago, IL" in prompt
    assert "never the verbatim \"block of\" phrase" in prompt
    assert "Wrong: `6500 block of South Hermitage Avenue, Chicago, IL`" in prompt
    assert "**Neighborhoods and regions**:" in prompt
    assert "Longfellow, Minneapolis, MN" in prompt
    assert "**Intersections**:" in prompt
    assert "Main Street and 2nd Street, Chicago, IL" in prompt
    assert "**Spans**:" in prompt
    assert "Lake Street from Nicollet Avenue to 28th Avenue, Minneapolis, MN" in prompt


def test_place_extract_prompt_only_text_is_json_path_placeholder() -> None:
    """Prose format templates like {City} must be escaped as {{City}} in extract.md."""
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    stripped = raw.replace("{{", "").replace("}}", "")
    placeholders = re.findall(r"\{([^}]+)\}", stripped)
    assert placeholders == ["text"]


def test_resolve_place_extract_prompt_prefers_live_bundled_snapshot() -> None:
    bundled = "Intro\nformat **`{{City}}, {{Country}}`**\nFooter {text}"
    stale_graph = "Intro\nformat **`{City}, {Country}`**\nFooter {text}"
    assert resolve_place_extract_prompt(bundled=bundled, custom=stale_graph) == bundled


def test_resolve_place_extract_prompt_keeps_true_custom_override() -> None:
    bundled = "Default extraction rules.\n{text}"
    custom = "Custom project rules only for us.\n{text}"
    assert resolve_place_extract_prompt(bundled=bundled, custom=custom) == custom


def test_substitute_prompt_placeholders_leaves_unknown_prose_tokens() -> None:
    template = "Format as `{City}, {Country}`.\n\n{text}"
    flattened = {
        "text": "Article body.",
        "article_metadata": {"category": "news_story"},
    }
    built = substitute_prompt_placeholders(
        template,
        flattened,
        extract_json_path=extract_json_path,
    )
    assert "{City}, {Country}" in built
    assert "Article body." in built


def test_normalize_prompt_for_comparison_unifies_brace_escapes() -> None:
    assert normalize_prompt_for_comparison("{{City}}, {{ST}}") == normalize_prompt_for_comparison(
        "{City}, {ST}"
    )
