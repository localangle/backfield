"""Tests that PersonExtract prompt includes institutional exclusion guidance."""

from __future__ import annotations

from pathlib import Path

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "packages"
    / "backfield-agate"
    / "src"
    / "agate_nodes"
    / "person_extract"
    / "prompts"
    / "extract.md"
)


def test_person_extract_prompt_includes_hard_stops_table() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "## Hard stops — the person test" in prompt
    assert "WBEZ reported" in prompt
    assert "American Medical Association announced" in prompt
    assert "Kittelson & Associates" in prompt
    assert "Engaged Capital" in prompt
    assert "Glenbard East" in prompt
    assert "ESPN 1000" in prompt
    assert "Presidential Records Act of 1978" in prompt
    assert "Buenos Aires" in prompt
    assert "Illinois General Assembly" in prompt
    assert "`CTA`, `DHS`, `PBS`" in prompt


def test_person_extract_prompt_includes_band_guidance() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "bands are people" in prompt
    assert "Pearl Jam" in prompt
    assert "Do not put bands in organization extraction" in prompt
