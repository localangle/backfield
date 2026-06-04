"""Person editorial vocabulary and field normalization."""

from __future__ import annotations

import unicodedata

PERSON_NATURE_VALUES: tuple[str, ...] = (
    "subject",
    "source",
    "expert",
    "official",
    "witness",
    "affected",
    "victim",
    "suspect",
    "participant",
    "observer",
    "context",
    "other",
)

# PersonExtract ``type`` → substrate / canonical ``person_type``
# (prompt: person_extract/prompts/extract.md).
PERSON_TYPE_VALUES: tuple[str, ...] = (
    "athlete",
    "coach",
    "sports_official",
    "sports_executive",
    "elected_official",
    "government_official",
    "political_staff",
    "lawyer_legal_advocate",
    "judge_court_official",
    "law_enforcement_public_safety",
    "crime_justice_subject",
    "business_owner_executive",
    "business_professional",
    "labor_union_representative",
    "artist_entertainer",
    "media_journalism",
    "arts_culture_professional",
    "education_research_expert",
    "healthcare_worker",
    "community_member",
    "unknown",
    "other",
)

PERSON_TYPE_LEGACY_ALIASES: dict[str, str] = {
    "politician": "elected_official",
    "musician": "artist_entertainer",
    "community member": "community_member",
    "law enforcement": "law_enforcement_public_safety",
}


def normalize_person_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def person_match_key(value: str | None) -> str:
    """Accent-insensitive key for person-name equality (display text unchanged elsewhere)."""
    normalized = normalize_person_text(value)
    if not normalized:
        return ""
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def person_names_match(a: str | None, b: str | None) -> bool:
    """True when both names share the same non-empty accent-folded match key."""
    key_a = person_match_key(a)
    key_b = person_match_key(b)
    return bool(key_a) and key_a == key_b


def normalize_person_type(value: str | None) -> str | None:
    """Map PersonExtract ``type`` to a bounded ``person_type`` slug."""
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    slug = cleaned.replace(" ", "_")
    mapped = PERSON_TYPE_LEGACY_ALIASES.get(cleaned) or PERSON_TYPE_LEGACY_ALIASES.get(slug)
    if mapped:
        slug = mapped
    if slug in PERSON_TYPE_VALUES:
        return slug
    return "other"


def person_alias_lookup_keys(value: str | None) -> tuple[str, ...]:
    """Stored ``normalized_alias`` variants for recall and exact alias lookup."""
    norm = normalize_person_text(value)
    if not norm:
        return ()
    folded = person_match_key(value)
    if folded != norm:
        return (norm, folded)
    return (norm,)


def normalize_person_sort_key(value: str | None) -> str | None:
    cleaned = normalize_person_text(value)
    return cleaned or None


def derive_person_sort_key(
    display_name: str | None,
    *,
    explicit: str | None = None,
    name_last: str | None = None,
) -> str | None:
    """Lowercase last-name (or sole token) used for person list ordering."""
    explicit_norm = normalize_person_sort_key(explicit)
    if explicit_norm:
        return explicit_norm
    last_norm = normalize_person_sort_key(name_last)
    if last_norm:
        return last_norm
    if display_name and display_name.strip():
        parts = display_name.strip().split()
        if len(parts) >= 2:
            return normalize_person_sort_key(parts[-1])
        return normalize_person_sort_key(parts[0])
    return None


def person_identity_fingerprint(
    *,
    normalized_name: str,
    title: str | None = None,
    affiliation: str | None = None,
) -> str:
    """Project-scoped dedupe hash for substrate person rows."""
    from backfield_stylebook.entity_types import compute_identity_fingerprint

    return compute_identity_fingerprint(
        "person",
        normalized_name=normalized_name,
        title=normalize_person_text(title),
        affiliation=normalize_person_text(affiliation),
    )
