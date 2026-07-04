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


def test_person_extract_prompt_includes_institutional_examples() -> None:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert "WBEZ reported" in prompt
    assert "American Medical Association said" in prompt
    assert "Kittelson & Associates" in prompt
    assert "Gibson Guitars" in prompt
    assert "Glenbard East" in prompt
    assert "Chicago Department of Transportation spokesperson" in prompt
    assert "CTA`, `DHS`, `FBI`, `MLB`, `UIC`, `WBEZ`" in prompt
