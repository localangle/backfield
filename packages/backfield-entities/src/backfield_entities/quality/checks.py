"""Registry of stylebook cleanup checks (surface-only triage).

This module is the **single source of truth** for which cleanup checks exist and
how each check's open-issue count is computed. The stylebook-api router derives
hub counts purely from this registry, so there is no per-check dispatch to keep
in sync.

To add a new cleanup check:

1. Implement a finder under ``quality/finders/`` exposing a ``count_*`` function
   (and a ``list_*``/``paginate_*`` function for the detail endpoint).
2. Register a :class:`CleanupCheckDef` below, wiring the finder's count via the
   ``count`` callable (it receives a :class:`CleanupCountContext`).
3. Add the matching list route in ``stylebook_api.routers.stylebook_cleanup`` and
   the frontend entry in ``apps/stylebook-ui/src/lib/cleanupChecks.ts``.

Keep the ``id`` here identical to the route segment and to the ``_CHECK_ID`` /
dismissal key used inside the finder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session

from backfield_entities.quality.finders.duplicate_locations import (
    count_duplicate_location_clusters,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    count_duplicate_organization_clusters,
)
from backfield_entities.quality.finders.duplicate_people import (
    count_duplicate_person_clusters,
)
from backfield_entities.quality.finders.location_geography_issues import (
    count_location_geography_issues,
)
from backfield_entities.quality.finders.location_name_mismatch import (
    count_location_name_mismatches,
)
from backfield_entities.quality.finders.organization_name_mismatch import (
    count_organization_name_mismatches,
)
from backfield_entities.quality.finders.person_name_mismatch import (
    count_person_name_mismatches,
)
from backfield_entities.quality.finders.questionable_organizations import (
    count_questionable_organization_canonicals,
)
from backfield_entities.quality.finders.questionable_people import (
    count_questionable_person_canonicals,
)

CleanupCheckKind = Literal["cluster", "list"]
CleanupEntityType = Literal["location", "person", "organization"]


@dataclass(frozen=True)
class CleanupCountContext:
    """Inputs available to every cleanup count function.

    Each check uses only the fields it needs; finders keep their own explicit
    signatures and the registry adapts them via each check's ``count`` callable.
    """

    stylebook_id: int
    organization_id: int
    full_threshold: float
    head_threshold: float


CleanupCountFn = Callable[[Session, CleanupCountContext], int]


@dataclass(frozen=True)
class CleanupCheckDef:
    id: str
    title: str
    description: str
    entity_type: CleanupEntityType
    kind: CleanupCheckKind
    count: CleanupCountFn


LOCATION_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-locations",
        title="Potential duplicate locations",
        description=(
            "Groups of location canonicals with the same name or a very similar primary "
            "name. Review each record and relink evidence or edit names manually."
        ),
        entity_type="location",
        kind="cluster",
        count=lambda session, ctx: count_duplicate_location_clusters(
            session,
            stylebook_id=ctx.stylebook_id,
            full_threshold=ctx.full_threshold,
            head_threshold=ctx.head_threshold,
        ),
    ),
    CleanupCheckDef(
        id="missing-geometry-locations",
        title="Potential missing or incorrect geographies",
        description=(
            "Location records with no stored geography, or linked places whose map "
            "location is far from the catalog record. Open each record to review."
        ),
        entity_type="location",
        kind="list",
        count=lambda session, ctx: count_location_geography_issues(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
    ),
    CleanupCheckDef(
        id="mismatched-locations",
        title="Potential mismatched places",
        description=(
            "Places with linked mentions whose names look unlike this record. "
            "Open each record to review the link."
        ),
        entity_type="location",
        kind="list",
        count=lambda session, ctx: count_location_name_mismatches(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
    ),
)

PERSON_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-people",
        title="Potential duplicate people",
        description=(
            "Groups of person canonicals with the same name or a very similar name. "
            "Review each record and relink evidence or edit names manually."
        ),
        entity_type="person",
        kind="cluster",
        count=lambda session, ctx: count_duplicate_person_clusters(
            session,
            stylebook_id=ctx.stylebook_id,
            full_threshold=ctx.full_threshold,
        ),
    ),
    CleanupCheckDef(
        id="mismatched-people",
        title="Potential mismatched people",
        description=(
            "People with linked mentions whose names look unlike this record. "
            "Open each record to review the link."
        ),
        entity_type="person",
        kind="list",
        count=lambda session, ctx: count_person_name_mismatches(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
    ),
    CleanupCheckDef(
        id="questionable-person-canonicals",
        title="Questionable person canonicals",
        description=(
            "Person records that may actually be organizations, agencies, schools, media "
            "outlets, teams, or unnamed roles. Review each record before treating it as a person."
        ),
        entity_type="person",
        kind="list",
        count=lambda session, ctx: count_questionable_person_canonicals(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
    ),
)

ORGANIZATION_CLEANUP_CHECKS: tuple[CleanupCheckDef, ...] = (
    CleanupCheckDef(
        id="duplicate-organizations",
        title="Potential duplicate organizations",
        description=(
            "Groups of organization canonicals with the same name or a very similar name. "
            "Review each record and relink evidence or edit names manually."
        ),
        entity_type="organization",
        kind="cluster",
        count=lambda session, ctx: count_duplicate_organization_clusters(
            session,
            stylebook_id=ctx.stylebook_id,
            full_threshold=ctx.full_threshold,
        ),
    ),
    CleanupCheckDef(
        id="mismatched-organizations",
        title="Potential mismatched organizations",
        description=(
            "Organizations with linked mentions whose names look unlike this record. "
            "Open each record to review the link."
        ),
        entity_type="organization",
        kind="list",
        count=lambda session, ctx: count_organization_name_mismatches(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
    ),
    CleanupCheckDef(
        id="questionable-organization-canonicals",
        title="Questionable organization canonicals",
        description=(
            "Organization canonicals that may actually be people, places, laws, programs, "
            "events, awards, or generic groups. Review each record before treating it as an "
            "organization."
        ),
        entity_type="organization",
        kind="list",
        count=lambda session, ctx: count_questionable_organization_canonicals(
            session,
            stylebook_id=ctx.stylebook_id,
            organization_id=ctx.organization_id,
        ),
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
