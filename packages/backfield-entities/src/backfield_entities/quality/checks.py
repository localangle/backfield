"""Registry of stylebook cleanup checks (surface-only triage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CleanupCheckKind = Literal["cluster", "list"]
CleanupEntityType = Literal["location"]


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
        title="Locations missing geography",
        description=(
            "Location canonicals with no stored geometry. Open each record to "
            "add a map pin or shape."
        ),
        entity_type="location",
        kind="list",
    ),
)


def cleanup_check_by_id(check_id: str) -> CleanupCheckDef | None:
    for check in LOCATION_CLEANUP_CHECKS:
        if check.id == check_id:
            return check
    return None
