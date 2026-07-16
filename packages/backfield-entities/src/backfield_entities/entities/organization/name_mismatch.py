"""High-precision detection of obviously wrong organization substrate-to-canonical links."""

from __future__ import annotations

from backfield_entities.entities.organization.types import (
    _ORGANIZATION_ACRONYM_STOP_WORDS,
    normalize_organization_text,
    organization_names_match_via_acronym,
)

# Shared institutional scaffolding that should not rescue a link by itself
# (e.g. "University of Maryland" vs "University of Minnesota Duluth").
_ORGANIZATION_INSTITUTION_STOP_WORDS: frozenset[str] = frozenset(
    {
        "university",
        "college",
        "school",
        "schools",
        "institute",
        "institution",
        "academy",
        "hospital",
        "hospitals",
        "center",
        "centre",
        "association",
        "society",
        "foundation",
        "department",
        "dept",
        "office",
        "bureau",
        "agency",
        "commission",
        "committee",
        "council",
        "board",
        "corp",
        "corporation",
        "inc",
        "llc",
        "ltd",
        "company",
        "group",
        "club",
        "team",
        "league",
    }
)


def _significant_tokens(value: str) -> frozenset[str]:
    norm = normalize_organization_text(value)
    if not norm:
        return frozenset()
    return frozenset(
        token
        for token in norm.split()
        if token and token not in _ORGANIZATION_ACRONYM_STOP_WORDS and len(token) >= 2
    )


def _distinctive_organization_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _significant_tokens(value)
        if token not in _ORGANIZATION_INSTITUTION_STOP_WORDS
    )


def organization_names_share_significant_token(left: str, right: str) -> bool:
    left_tokens = _significant_tokens(left)
    right_tokens = _significant_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return bool(left_tokens.intersection(right_tokens))


def organization_distinctive_tokens_conflict(left: str, right: str) -> bool:
    """True when both names have distinctive tokens and none of them overlap."""
    left_tokens = _distinctive_organization_tokens(left)
    right_tokens = _distinctive_organization_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens.isdisjoint(right_tokens)


def organization_link_is_obvious_mismatch(
    *,
    substrate_name: str,
    canonical_label: str,
    editorial_alias_keys: frozenset[str] | set[str] | None = None,
) -> bool:
    """True when a linked substrate name is clearly not the same organization as the label."""
    substrate_norm = normalize_organization_text(substrate_name)
    canonical_norm = normalize_organization_text(canonical_label)
    if not substrate_norm or not canonical_norm:
        return False
    if substrate_norm == canonical_norm:
        return False
    if organization_names_match_via_acronym(substrate_name, canonical_label):
        return False
    alias_keys = editorial_alias_keys or frozenset()
    if substrate_norm in alias_keys:
        return False
    if organization_distinctive_tokens_conflict(substrate_name, canonical_label):
        return True
    if organization_names_share_significant_token(substrate_name, canonical_label):
        return False
    return True
