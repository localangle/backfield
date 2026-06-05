"""Person name token overlap for recall and catalog search."""

from __future__ import annotations

from backfield_entities.entities.person.name_match import (
    person_name_tokens,
    score_person_name_overlap,
    significant_search_tokens,
)
from backfield_entities.entities.person.types import (
    person_alias_lookup_keys,
    person_match_key,
    person_names_match,
)


def test_person_match_key_folds_accents() -> None:
    assert person_match_key("Gina Ramírez") == person_match_key("Gina Ramirez")
    assert person_names_match("José García", "Jose Garcia")


def test_person_alias_lookup_keys_include_folded_variant() -> None:
    keys = person_alias_lookup_keys("Gina Ramírez")
    assert "gina ramírez" in keys
    assert "gina ramirez" in keys


def test_person_name_tokens_strips_middle_initial() -> None:
    given, family, tokens = person_name_tokens("Ronald L. Wyden")
    assert given == "ronald"
    assert family == "wyden"
    assert "l" not in tokens


def test_ronald_wyden_matches_ron_wyden() -> None:
    score = score_person_name_overlap("Ronald L. Wyden", "Ron Wyden")
    assert score >= 90


def test_accent_variant_scores_as_exact_name_overlap() -> None:
    score = score_person_name_overlap("José García", "Jose Garcia")
    assert score >= 100


def test_significant_search_tokens_includes_surname_and_given() -> None:
    toks = significant_search_tokens("Ronald L. Wyden")
    assert "wyden" in toks
    assert "ronald" in toks
