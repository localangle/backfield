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


def test_organization_extract_prompt_includes_decision_gate_and_paired_examples() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "## Organization decision gate" in prompt
    assert "omit `Grant Park`; keep `Grant Park Advisory Council`" in prompt
    assert "omit `Affordable Care Act`" in prompt
    assert "omit `Anti-Weaponization Fund`" in prompt
    assert "omit `A Mighty Wind`" in prompt
    assert "omit `American Community Survey`" in prompt
    assert "omit `Anne Frank House`" in prompt
    assert "omit `American civil society`" in prompt
    assert "Antonio Martínez Ocasio" in prompt
    assert "omit `Area 5 detectives`" in prompt
    assert "Never choose `government` or `other`" in prompt


def test_organization_extract_prompt_excludes_brands_and_bands() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "omit `Budweiser`" in prompt
    assert "Budweiser employees union" in prompt
    assert "Google executive team" in prompt
    assert "Pearl Jam" in prompt
    assert "Musical groups, bands, and recording acts" in prompt
