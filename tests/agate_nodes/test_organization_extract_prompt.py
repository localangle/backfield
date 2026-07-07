"""Tests that OrganizationExtract prompt includes tightened exclusion guidance."""

from __future__ import annotations

from pathlib import Path

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "packages"
    / "backfield-agate"
    / "src"
    / "agate_nodes"
    / "organization_extract"
    / "prompts"
    / "extract.md"
)


def test_organization_extract_prompt_includes_hard_stops_table() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "## Hard stops — the organization test" in prompt
    assert "Grant Park Advisory Council" in prompt
    assert "Affordable Care Act" in prompt
    assert "Anti-Weaponization Fund" in prompt
    assert "A Mighty Wind" in prompt
    assert "American Community Survey" in prompt
    assert "Anne Frank House" in prompt
    assert "American civil society" in prompt
    assert "Area 5 detectives" in prompt
    assert "Illinois police departments" in prompt
    assert "Illinois DMVs" in prompt
    assert "Illinois state law" in prompt
    assert "Never choose `government` or `other`" in prompt


def test_organization_extract_prompt_excludes_brands_and_bands() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "`Budweiser`, `Google`, `Coca-Cola`" in prompt
    assert "Budweiser employees union" in prompt
    assert "Google executive team" in prompt
    assert "Pearl Jam" in prompt
    assert "Bands and musical acts" in prompt
    assert "bands belong in **people** extraction" in prompt
