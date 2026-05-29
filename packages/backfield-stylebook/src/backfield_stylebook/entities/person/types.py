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
