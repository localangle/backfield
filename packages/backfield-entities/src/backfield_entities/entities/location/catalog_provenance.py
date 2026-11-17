"""Provenance strings that mark intentional Stylebook catalog rows (not ingest ghosts)."""

from __future__ import annotations

LOCATION_CATALOG_EDITORIAL_PROVENANCES: frozenset[str] = frozenset(
    {
        "stylebook_ui_manual",
        "stylebook_ui_import_csv",
        "stylebook_ui_accept",
        "stylebook_bundle_import",
        "stylebook_ui_link",
    }
)

# Aliases written when a cleanup decision folded another record into this one. They record that a
# person (or an approved review) judged the old name to be this place, so link checks trust them.
# They do not make a catalog row "editorial" for pruning, which keeps the set above unchanged.
LOCATION_CLEANUP_ALIAS_PROVENANCES: frozenset[str] = frozenset(
    {
        "stylebook_cleanup_merge",
        "stylebook_cleanup_ai_review",
    }
)


def is_location_catalog_editorial_provenance(provenance: str | None) -> bool:
    if provenance is None:
        return False
    return str(provenance).strip() in LOCATION_CATALOG_EDITORIAL_PROVENANCES


def is_location_alias_trusted_for_link_checks(provenance: str | None) -> bool:
    """True when an alias should rescue a linked mention from the name-mismatch checks."""
    if provenance is None:
        return False
    return (
        is_location_catalog_editorial_provenance(provenance)
        or str(provenance).strip() in LOCATION_CLEANUP_ALIAS_PROVENANCES
    )
