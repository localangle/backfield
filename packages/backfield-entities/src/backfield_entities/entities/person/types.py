"""Person editorial vocabulary and field normalization."""

from __future__ import annotations

import re

from backfield_entities.text.match_normalize import (
    alias_lookup_keys,
    match_fold_key,
    normalize_match_text,
)

# Strip punctuation so initials like ``C.J.`` fold to the same key as ``CJ``.
_PERSON_KEY_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_PERSON_KEY_WS_RE = re.compile(r"\s+")

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
    return normalize_match_text(value)


def person_match_key(value: str | None) -> str:
    """Accent- and punctuation-insensitive key for person-name equality.

    Display text is unchanged elsewhere. Periods and other non-alphanumerics are
    removed so ``C.J. Stroud`` and ``CJ Stroud`` share a key.
    """
    folded = match_fold_key(value)
    if not folded:
        return ""
    stripped = _PERSON_KEY_PUNCT_RE.sub("", folded)
    return _PERSON_KEY_WS_RE.sub(" ", stripped).strip()


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
    """Stored ``normalized_alias`` variants for recall and exact alias lookup.

    Includes literal + accent-folded forms plus the punctuation-stripped
    ``person_match_key`` so dotted initials hit both stored shapes.
    """
    keys = list(alias_lookup_keys(value))
    folded = person_match_key(value)
    if folded and folded not in keys:
        keys.append(folded)
    return tuple(keys)


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


_PERSON_GENERATIONAL_SUFFIX_TOKENS: frozenset[str] = frozenset(
    {"jr", "sr", "ii", "iii", "iv", "junior", "senior"}
)


def person_generational_suffix_key(normalized_name: str) -> str:
    """Terminal generational suffix token when present (``jr``, ``iii``, etc.)."""
    key = person_match_key(normalized_name)
    if not key:
        return ""
    tokens = key.split()
    if not tokens:
        return ""
    last = tokens[-1]
    if last in _PERSON_GENERATIONAL_SUFFIX_TOKENS:
        return last
    return ""


def person_identity_fingerprint(
    *,
    normalized_name: str,
    affiliation: str | None = None,
) -> str:
    """Project-scoped dedupe hash for substrate person rows.

    Uses accent-folded name (``person_match_key``) plus affiliation and optional
    generational suffix (``Jr.`` vs ``III``). Title/position is intentionally
    excluded — it is volatile per article and is not used for canonical tier-1
    strong match either.
    """
    from backfield_entities.registry.entity_types import compute_identity_fingerprint

    name_key = person_match_key(normalized_name)
    if not name_key:
        name_key = normalize_person_text(normalized_name)
    suffix_key = person_generational_suffix_key(normalized_name)
    return compute_identity_fingerprint(
        "person",
        normalized_name=name_key,
        affiliation=normalize_person_text(affiliation),
        generational_suffix=suffix_key,
    )
