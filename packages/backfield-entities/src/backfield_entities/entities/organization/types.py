"""Organization editorial vocabulary and field normalization."""

from __future__ import annotations

from backfield_entities.text.match_normalize import (
    alias_lookup_keys,
    match_fold_key,
    normalize_match_text,
)

ORGANIZATION_NATURE_VALUES: tuple[str, ...] = (
    "primary",
    "actor",
    "source",
    "subject",
    "affected",
    "regulator",
    "context",
    "other",
)

GENERATED_ACRONYM_PROVENANCE = "generated_acronym"

# OrganizationExtract ``type`` → substrate / canonical ``organization_type``.
ORGANIZATION_TYPE_VALUES: tuple[str, ...] = (
    "government",
    "law_enforcement",
    "court",
    "legislative_body",
    "political_party",
    "school_district",
    "school",
    "university",
    "hospital",
    "public_health",
    "public_services",
    "utilities",
    "company",
    "local_business",
    "financial_institution",
    "real_estate",
    "nonprofit",
    "community_group",
    "religious_org",
    "culture_arts",
    "sports_team",
    "sports_league",
    "media",
    "other",
)


def normalize_organization_text(value: str | None) -> str:
    return normalize_match_text(value)


def organization_match_key(value: str | None) -> str:
    return match_fold_key(value)


_ORGANIZATION_ACRONYM_STOP_WORDS: frozenset[str] = frozenset(
    {"a", "an", "the", "of", "and", "for", "in", "on", "at", "to"},
)


def organization_acronym_from_name(value: str | None) -> str | None:
    """Initialism from significant tokens (e.g. Chicago Public Schools → cps)."""
    norm = normalize_organization_text(value)
    if not norm:
        return None
    words = [w for w in norm.split() if w not in _ORGANIZATION_ACRONYM_STOP_WORDS]
    if len(words) < 2:
        return None
    letters = "".join(w[0] for w in words if w)
    if len(letters) < 2 or len(letters) > 8:
        return None
    return letters


def organization_looks_like_acronym(value: str | None) -> bool:
    """Short single-token name that may be an institutional initialism."""
    norm = normalize_organization_text(value)
    if not norm or " " in norm:
        return False
    return 2 <= len(norm) <= 6 and norm.isalpha()


def organization_names_match_via_acronym(left: str | None, right: str | None) -> bool:
    """True when one side is the initialism of the other."""
    left_norm = normalize_organization_text(left)
    right_norm = normalize_organization_text(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if multiword_organization_names_share_ambiguous_acronym(left_norm, right_norm):
        return False
    left_acr = organization_acronym_from_name(left_norm)
    right_acr = organization_acronym_from_name(right_norm)
    if left_acr and left_acr == right_norm:
        return True
    if right_acr and right_acr == left_norm:
        return True
    return False


def multiword_organization_names_share_ambiguous_acronym(
    left_norm: str,
    right_norm: str,
) -> bool:
    """True when two different multi-word names collapse to the same derived acronym."""
    if not left_norm or not right_norm or left_norm == right_norm:
        return False
    if " " not in left_norm or " " not in right_norm:
        return False
    left_acr = organization_acronym_from_name(left_norm)
    right_acr = organization_acronym_from_name(right_norm)
    return bool(left_acr and left_acr == right_acr)


def organization_tier1_identity_compatible(
    *,
    substrate_norm: str,
    canonical_label_norm: str,
) -> bool:
    """Whether rules-based tier-1 auto-link may treat two names as the same organization."""
    if not substrate_norm or not canonical_label_norm:
        return False
    if substrate_norm == canonical_label_norm:
        return True
    if multiword_organization_names_share_ambiguous_acronym(
        substrate_norm,
        canonical_label_norm,
    ):
        return False
    return organization_names_match_via_acronym(substrate_norm, canonical_label_norm)


def organization_literal_label_identity_compatible(
    *,
    substrate_norm: str,
    canonical_label_norm: str,
) -> bool:
    """Tier-1 identity where only a literal canonical acronym is trusted."""
    if not organization_tier1_identity_compatible(
        substrate_norm=substrate_norm,
        canonical_label_norm=canonical_label_norm,
    ):
        return False
    if substrate_norm == canonical_label_norm:
        return True
    if organization_looks_like_acronym(substrate_norm) and " " in canonical_label_norm:
        return False
    return True


def organization_alias_surface_form(label: str, normalized_key: str) -> str:
    """Display text stored on alias rows for a lookup key."""
    clean = label.strip()
    acr = organization_acronym_from_name(clean)
    if acr and acr == normalized_key:
        return normalized_key.upper()
    return clean


def organization_canonical_alias_keys(value: str | None) -> tuple[str, ...]:
    """Alias keys stored on a canonical label or linked substrate name."""
    norm = normalize_organization_text(value)
    if not norm:
        return ()
    keys: list[str] = list(alias_lookup_keys(value))
    acr = organization_acronym_from_name(value)
    if acr and acr != norm and acr not in keys:
        keys.append(acr)
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


def organization_canonical_alias_entries(value: str | None) -> tuple[tuple[str, bool], ...]:
    """Canonical alias keys paired with whether each key is a derived acronym."""
    norm = normalize_organization_text(value)
    acronym = organization_acronym_from_name(value)
    return tuple(
        (key, bool(acronym and acronym != norm and key == acronym))
        for key in organization_canonical_alias_keys(value)
    )


def organization_substrate_alias_lookup_keys(value: str | None) -> tuple[str, ...]:
    """Lookup keys when matching a substrate name against stored aliases."""
    return alias_lookup_keys(value)


# Backward-compatible alias for canonical seeding call sites.
organization_alias_lookup_keys = organization_canonical_alias_keys


def normalize_organization_type(value: str | None) -> str | None:
    """Map OrganizationExtract ``type`` to a bounded ``organization_type`` slug."""
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    slug = cleaned.replace(" ", "_")
    if slug in ORGANIZATION_TYPE_VALUES:
        return slug
    return "other"


# Editorial near-equivalences for canonical link when name/alias already matches.
_ORGANIZATION_TYPE_LINK_COMPATIBILITY_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"company", "local_business"}),
    frozenset({"nonprofit", "community_group", "religious_org"}),
    frozenset({"financial_institution", "company", "local_business"}),
    frozenset({"real_estate", "company", "local_business"}),
    frozenset({"media", "company"}),
    frozenset({"culture_arts", "nonprofit", "community_group"}),
)


def organization_types_are_link_compatible(
    left: str | None,
    right: str | None,
) -> bool:
    """True when two organization_type slugs may denote the same institution."""
    left_norm = normalize_organization_type(left)
    right_norm = normalize_organization_type(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    for group in _ORGANIZATION_TYPE_LINK_COMPATIBILITY_GROUPS:
        if left_norm in group and right_norm in group:
            return True
    return False


def organization_identity_fingerprint(
    *,
    normalized_name: str,
    organization_type: str | None = None,
) -> str:
    """Project-scoped dedupe hash for substrate organization rows."""
    from backfield_entities.registry.entity_types import compute_identity_fingerprint

    return compute_identity_fingerprint(
        "organization",
        normalized_name=normalized_name,
        organization_type=normalize_organization_type(organization_type),
    )
