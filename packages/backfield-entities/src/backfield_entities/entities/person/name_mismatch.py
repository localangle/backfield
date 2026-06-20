"""High-precision detection of obviously wrong person substrate-to-canonical links."""

from __future__ import annotations

from backfield_entities.entities.person.name_match import (
    person_name_tokens,
    score_person_name_overlap,
)
from backfield_entities.entities.person.types import person_match_key, person_names_match


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
    if score_person_name_overlap(substrate_name, canonical_label) > 0:
        return False
    alias_keys = editorial_alias_keys or frozenset()
    substrate_key = person_match_key(substrate_name)
    if substrate_key and substrate_key in alias_keys:
        return False
    return True
