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
    assert "People with appended geography" in prompt
    assert "Brandon Johnson, Chicago, IL" in prompt
    assert "Sports teams, games, leagues, divisions, eras, and associations" in prompt
    assert "Bears-Packers game" in prompt
    assert "Game 7" in prompt
    assert "1969 Bears" in prompt
    assert "American Basketball Association" in prompt
    assert "American League Central" in prompt
    assert "Eastern Conference" in prompt
    assert "Athletic districts and scholastic conferences" in prompt
    assert "West Suburban Conference Silver" in prompt
    assert "Demographic and identity-based area labels" in prompt
    assert "Black neighborhoods, Chicago, IL" in prompt
    assert "Broad descriptive macro-areas" in prompt
    assert "Forty States, US" in prompt
    assert "International cities" in prompt
    assert "Paris, France" in prompt
    assert "Washington, DC vs Washington state" in prompt
    assert "Street-type spelling" in prompt
    assert "103rd Street, Chicago, IL" in prompt
    assert "Training camps, combines, drafts, tournaments, and event names" in prompt
    assert "NFL Scouting Combine" in prompt
    assert "Venue interiors and subparts" in prompt
    assert "concession stand" in prompt
    assert "dugout" in prompt
    assert "Organization names with inferred headquarters or branch geocodes" in prompt
    assert "American Medical Association, IL" in prompt


def test_place_extract_prompt_includes_historical_nature() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "**historical**" in prompt
    assert "past events, precedent, or historical comparison" in prompt


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
