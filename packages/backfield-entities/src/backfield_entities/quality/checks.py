"""Registry of stylebook cleanup checks (surface-only triage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CleanupCheckKind = Literal["cluster", "list"]
CleanupEntityType = Literal["location", "person", "organization"]


@dataclass(frozen=True)
class CleanupCheckDef:
    id: str
    title: str
    description: str
    entity_type: CleanupEntityType
    kind: CleanupCheckKind


LOCATION_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-locations",
        title="Possible duplicate locations",
        description=(
            "Groups of location canonicals with the same name or a very similar primary "
            "name. Review each record and relink evidence or edit names manually."
        ),
        entity_type="location",
        kind="cluster",
    ),
    CleanupCheckDef(
        id="missing-geometry-locations",
        title="Missing or potentially incorrect geographies",
        description=(
            "Location records with no stored geography, or linked places whose map "
            "location is far from the catalog record. Open each record to review."
        ),
        entity_type="location",
        kind="list",
    ),
)

PERSON_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-people",
        title="Possible duplicate people",
        description=(
            "Groups of person canonicals with the same name or a very similar name. "
            "Review each record and relink evidence or edit names manually."
        ),
        entity_type="person",
        kind="cluster",
    ),
    CleanupCheckDef(
        id="mismatched-people",
        title="Possibly mismatched people",
        description=(
            "People with linked mentions whose names look unlike this record. "
            "Open each record to review the link."
        ),
        entity_type="person",
        kind="list",
    ),
)

ORGANIZATION_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-organizations",
        title="Possible duplicate organizations",
        description=(
            "Groups of organization canonicals with the same name or a very similar name. "
            "Review each record and relink evidence or edit names manually."
        ),
        entity_type="organization",
        kind="cluster",
    ),
    CleanupCheckDef(
        id="mismatched-organizations",
        title="Possibly mismatched organizations",
        description=(
            "Organizations with linked mentions whose names look unlike this record. "
            "Open each record to review the link."
        ),
        entity_type="organization",
        kind="list",
    ),
)

STYLEBOOK_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    *LOCATION_CLEANUP_CHECKS,
    *PERSON_CLEANUP_CHECKS,
    *ORGANIZATION_CLEANUP_CHECKS,
)


def cleanup_check_by_id(check_id: str) -> CleanupCheckDef | None:
    for check in STYLEBOOK_CLEANUP_CHECKS:
        if check.id == check_id:
            return check
    return None
