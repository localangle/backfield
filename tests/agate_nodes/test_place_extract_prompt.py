"""Tests that PlaceExtract prompt excludes non-geographic candidates."""

from __future__ import annotations

from pathlib import Path

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
    assert "Sports teams, leagues, divisions, eras, and associations" in prompt
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
    assert "Organization names with inferred headquarters or branch geocodes" in prompt
    assert "American Medical Association, IL" in prompt
