"""Person name token overlap for recall and catalog search."""

from __future__ import annotations

from backfield_stylebook.entities.person.name_match import (
    person_name_tokens,
    score_person_name_overlap,
    significant_search_tokens,
)


def test_person_name_tokens_strips_middle_initial() -> None:
    given, family, tokens = person_name_tokens("Ronald L. Wyden")
    assert given == "ronald"
    assert family == "wyden"
    assert "l" not in tokens


def test_ronald_wyden_matches_ron_wyden() -> None:
    score = score_person_name_overlap("Ronald L. Wyden", "Ron Wyden")
    assert score >= 90


def test_significant_search_tokens_includes_surname_and_given() -> None:
    toks = significant_search_tokens("Ronald L. Wyden")
    assert "wyden" in toks
    assert "ronald" in toks
