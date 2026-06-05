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
