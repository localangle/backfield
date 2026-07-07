"""Tests for PersonExtract prompt resolution."""

from __future__ import annotations

from agate_nodes.person_extract.prompt_template import resolve_person_extract_prompt


def test_resolve_person_extract_prompt_prefers_bundled_when_snapshot_matches() -> None:
    bundled = "Extract people.\n\nReturn {{ \"people\": [] }}.\n\n{text}"
    custom = 'Extract people.\n\nReturn { "people": [] }.\n\n{text}'
    assert resolve_person_extract_prompt(bundled=bundled, custom=custom) == bundled


def test_resolve_person_extract_prompt_keeps_real_custom_prompt() -> None:
    bundled = "Extract people from {text}"
    custom = "Only extract elected officials from {text}"
    assert resolve_person_extract_prompt(bundled=bundled, custom=custom) == custom


def test_resolve_person_extract_prompt_uses_bundled_when_custom_empty() -> None:
    bundled = "Extract people from {text}"
    assert resolve_person_extract_prompt(bundled=bundled, custom="") == bundled
