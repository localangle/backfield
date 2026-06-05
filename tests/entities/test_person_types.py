"""PersonExtract ``person_type`` taxonomy normalization."""

from __future__ import annotations

from backfield_entities.entities.person.types import (
    PERSON_TYPE_VALUES,
    normalize_person_type,
    person_names_match,
)


def test_person_type_values_include_unknown_and_other() -> None:
    assert "unknown" in PERSON_TYPE_VALUES
    assert "other" in PERSON_TYPE_VALUES
    assert len(PERSON_TYPE_VALUES) == 22


def test_normalize_person_type_accepts_taxonomy_slugs() -> None:
    assert normalize_person_type(" elected_official ") == "elected_official"
    assert normalize_person_type("community_member") == "community_member"


def test_normalize_person_type_maps_legacy_free_form_values() -> None:
    assert normalize_person_type("politician") == "elected_official"
    assert normalize_person_type("musician") == "artist_entertainer"
    assert normalize_person_type("community member") == "community_member"


def test_normalize_person_type_unknown_slug_is_unknown() -> None:
    assert normalize_person_type("unknown") == "unknown"


def test_normalize_person_type_invalid_becomes_other() -> None:
    assert normalize_person_type("astronaut") == "other"


def test_normalize_person_type_empty_is_none() -> None:
    assert normalize_person_type("") is None
    assert normalize_person_type(None) is None


def test_person_names_match_still_folds_accents() -> None:
    assert person_names_match("José García", "Jose Garcia")
