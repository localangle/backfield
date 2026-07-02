"""Editorial prose normalization helpers."""

from __future__ import annotations

from backfield_entities.editorial_text import normalize_editorial_prose


def test_normalize_editorial_prose_capitalizes_first_character() -> None:
    assert normalize_editorial_prose("sophomore") == "Sophomore"
    assert (
        normalize_editorial_prose("boys basketball team in game coverage")
        == "Boys basketball team in game coverage"
    )


def test_normalize_editorial_prose_preserves_existing_casing() -> None:
    assert (
        normalize_editorial_prose("Central player and quoted defender")
        == "Central player and quoted defender"
    )


def test_normalize_editorial_prose_empty_values() -> None:
    assert normalize_editorial_prose(None) is None
    assert normalize_editorial_prose("") is None
    assert normalize_editorial_prose("   ") is None
