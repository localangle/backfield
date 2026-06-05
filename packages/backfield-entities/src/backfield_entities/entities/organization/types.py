"""Organization editorial vocabulary and field normalization."""

from __future__ import annotations

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
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


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
    left_acr = organization_acronym_from_name(left_norm)
    right_acr = organization_acronym_from_name(right_norm)
    if left_acr and left_acr == right_norm:
        return True
    if right_acr and right_acr == left_norm:
        return True
    return False


def organization_alias_surface_form(label: str, normalized_key: str) -> str:
    """Display text stored on alias rows for a lookup key."""
    clean = label.strip()
    acr = organization_acronym_from_name(clean)
    if acr and acr == normalized_key:
        return normalized_key.upper()
    return clean


def organization_alias_lookup_keys(value: str | None) -> tuple[str, ...]:
    """Stored ``normalized_alias`` variants for recall and exact alias lookup."""
    norm = normalize_organization_text(value)
    if not norm:
        return ()
    keys: list[str] = [norm]
    acr = organization_acronym_from_name(value)
    if acr and acr != norm:
        keys.append(acr)
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


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
