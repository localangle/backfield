"""Person editorial vocabulary and field normalization."""

from __future__ import annotations

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


def normalize_person_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


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
