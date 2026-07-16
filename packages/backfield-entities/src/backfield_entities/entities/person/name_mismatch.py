"""High-precision detection of obviously wrong person substrate-to-canonical links."""

from __future__ import annotations

from backfield_entities.entities.person.name_match import (
    given_names_compatible,
    person_name_tokens,
    score_person_name_overlap,
)
from backfield_entities.entities.person.types import person_match_key, person_names_match


def person_given_names_conflict(substrate_name: str, canonical_label: str) -> bool:
    """True when both sides share a family name but have incompatible given names.

    Catches same-surname blunders (Kam Jones → Tre Jones) while allowing prefix
    nicknames (Rob/Robert). Single-token names are never treated as conflicts.
    """
    s_given, s_family, s_tokens = person_name_tokens(substrate_name)
    c_given, c_family, c_tokens = person_name_tokens(canonical_label)
    if len(s_tokens) < 2 or len(c_tokens) < 2:
        return False
    if not s_family or not c_family or s_family != c_family:
        return False
    if not s_given or not c_given:
        return False
    return not given_names_compatible(s_given, c_given)


def person_link_is_obvious_mismatch(
    *,
    substrate_name: str,
    canonical_label: str,
    editorial_alias_keys: frozenset[str] | set[str] | None = None,
) -> bool:
    """True when a linked substrate name is clearly not the same person as the canonical label.

    Requires a surname token on the substrate row (single-token nicknames are excluded).
    """
    _given, _family, tokens = person_name_tokens(substrate_name)
    if len(tokens) < 2:
        return False
    if person_names_match(substrate_name, canonical_label):
        return False
    alias_keys = editorial_alias_keys or frozenset()
    substrate_key = person_match_key(substrate_name)
    if substrate_key:
        for alias_key in alias_keys:
            # Compare via person_match_key so dotted vs undotted aliases match.
            if person_match_key(alias_key) == substrate_key:
                return False
            if person_names_match(substrate_name, alias_key):
                return False
    if person_given_names_conflict(substrate_name, canonical_label):
        return True
    if score_person_name_overlap(substrate_name, canonical_label) > 0:
        return False
    return True
