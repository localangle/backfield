"""Provenance strings that mark intentional Stylebook catalog rows (not ingest ghosts)."""

from __future__ import annotations

from backfield_entities.entities.cleanup_alias_provenance import CLEANUP_API_ALIAS_PROVENANCE

ORGANIZATION_CATALOG_EDITORIAL_PROVENANCES: frozenset[str] = frozenset(
    {
        "stylebook_agent_organization_maintenance",
        CLEANUP_API_ALIAS_PROVENANCE,
        "stylebook_ui_manual",
        "stylebook_ui_import_csv",
        "stylebook_ui_accept",
        "stylebook_bundle_import",
        "stylebook_ui_link",
    }
)


def is_organization_catalog_editorial_provenance(provenance: str | None) -> bool:
    if provenance is None:
        return False
    return str(provenance).strip() in ORGANIZATION_CATALOG_EDITORIAL_PROVENANCES
