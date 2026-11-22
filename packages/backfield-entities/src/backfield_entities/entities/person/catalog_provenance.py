"""Provenance strings that mark intentional Stylebook catalog rows (not ingest ghosts)."""

from __future__ import annotations

# Alias provenance values that must never be removed by ingest orphan cleanup.
PERSON_CATALOG_EDITORIAL_PROVENANCES: frozenset[str] = frozenset(
    {
        "stylebook_ui_manual",
        "stylebook_ui_import_csv",
        "stylebook_ui_accept",
        "stylebook_bundle_import",
        "stylebook_ui_link",
    }
)

PERSON_CLEANUP_ALIAS_PROVENANCES: frozenset[str] = frozenset(
    {
        "stylebook_cleanup_merge",
        "stylebook_cleanup_ai_review",
        "stylebook_cleanup_2024_people",
    }
)


def is_person_catalog_editorial_provenance(provenance: str | None) -> bool:
    if provenance is None:
        return False
    return str(provenance).strip() in PERSON_CATALOG_EDITORIAL_PROVENANCES


def is_person_alias_trusted_for_link_checks(provenance: str | None) -> bool:
    """Return whether an alias represents an explicit person identity decision."""
    if provenance is None:
        return False
    return (
        is_person_catalog_editorial_provenance(provenance)
        or str(provenance).strip() in PERSON_CLEANUP_ALIAS_PROVENANCES
    )
