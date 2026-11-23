"""One apply path for merging a canonical into another, for every entity type.

Runs the entity's merge, writes the activity row, and queues the semantic reindex through a
caller-supplied function. It does not commit: the caller owns the transaction. Nothing here
imports a queue client, so any app can pass its own reindex adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlmodel import Session

from backfield_entities.activity import (
    EVENT_CLEANUP_MERGE,
    ActorType,
    log_stylebook_activity_safe,
)
from backfield_entities.cleanup.redirects import record_redirect
from backfield_entities.entities.location.merge import (
    GeometryWinner,
    merge_location_canonical_into,
)
from backfield_entities.entities.organization.merge import merge_organization_canonical_into
from backfield_entities.entities.person.merge import merge_person_canonical_into

MergeEntityType = Literal["location", "person", "organization"]

DEFAULT_MERGE_PROVENANCE = "stylebook_cleanup_merge"


class ReindexEntity(Protocol):
    """Queue semantic reindex jobs for one relinked entity (a Stylebook-API or Core-API adapter)."""

    def __call__(
        self,
        session: Session,
        *,
        project_id: int,
        entity_type: MergeEntityType,
        entity_id: int,
    ) -> None: ...


@dataclass(frozen=True)
class MergeActivity:
    """The activity row to write for a merge; leave it out to write none."""

    actor_type: ActorType | str
    actor_user_id: int | None = None
    source: str = "cleanup_check"
    # Extra facts for the row, such as ``check_id``, ``run_id``, or the key that made the change.
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MergeRequest:
    entity_type: MergeEntityType
    stylebook_id: int
    organization_id: int
    source_canonical_id: str
    target_canonical_id: str
    provenance: str = DEFAULT_MERGE_PROVENANCE
    # Location, person, or organization kind to use when the two records disagree.
    resolved_type: str | None = None
    # Locations only: which record's geography wins when both have one.
    geometry_winner: GeometryWinner = "target"


@dataclass(frozen=True)
class MergeOutcome:
    entity_type: MergeEntityType
    source_id: str
    target_id: str
    source_label: str | None
    target_label: str | None
    relinked_substrate_count: int
    relinked_substrates: tuple[tuple[int, int], ...]
    source_deleted: bool
    transferred_alias_count: int
    transferred_meta_count: int
    # Locations only: source geography the survivor did not take, so it is never lost silently.
    unapplied_source_geometry: dict[str, Any] | None


def _canonical_label(
    session: Session, *, entity_type: MergeEntityType, stylebook_id: int, canonical_id: str
) -> str | None:
    model: type[Any]
    if entity_type == "location":
        model = StylebookLocationCanonical
    elif entity_type == "person":
        model = StylebookPersonCanonical
    else:
        model = StylebookOrganizationCanonical
    row = session.get(model, canonical_id.strip())
    if row is None or int(row.stylebook_id) != int(stylebook_id):
        return None
    return str(row.label).strip() or None


def _run_merge(session: Session, request: MergeRequest) -> MergeOutcome:
    common: dict[str, Any] = {
        "stylebook_id": request.stylebook_id,
        "organization_id": request.organization_id,
        "source_canonical_id": request.source_canonical_id,
        "target_canonical_id": request.target_canonical_id,
        "provenance": request.provenance,
    }
    source_label = _canonical_label(
        session,
        entity_type=request.entity_type,
        stylebook_id=request.stylebook_id,
        canonical_id=request.source_canonical_id,
    )
    target_label = _canonical_label(
        session,
        entity_type=request.entity_type,
        stylebook_id=request.stylebook_id,
        canonical_id=request.target_canonical_id,
    )
    if request.entity_type == "location":
        location = merge_location_canonical_into(
            session, **common, geometry_winner=request.geometry_winner
        )
        return MergeOutcome(
            entity_type="location",
            source_id=location.source_id,
            target_id=location.target_id,
            source_label=source_label,
            target_label=target_label,
            relinked_substrate_count=location.relinked_substrate_count,
            relinked_substrates=location.relinked_substrates,
            source_deleted=location.source_deleted,
            transferred_alias_count=location.transferred_alias_count,
            transferred_meta_count=location.transferred_meta_count,
            unapplied_source_geometry=location.unapplied_source_geometry,
        )
    if request.entity_type == "person":
        person = merge_person_canonical_into(
            session, **common, resolved_person_type=request.resolved_type
        )
        return MergeOutcome(
            entity_type="person",
            source_id=person.source_id,
            target_id=person.target_id,
            source_label=source_label,
            target_label=target_label,
            relinked_substrate_count=person.relinked_substrate_count,
            relinked_substrates=person.relinked_substrates,
            source_deleted=person.source_deleted,
            transferred_alias_count=person.transferred_alias_count,
            transferred_meta_count=person.transferred_meta_count,
            unapplied_source_geometry=None,
        )
    organization = merge_organization_canonical_into(
        session, **common, resolved_organization_type=request.resolved_type
    )
    return MergeOutcome(
        entity_type="organization",
        source_id=organization.source_id,
        target_id=organization.target_id,
        source_label=source_label,
        target_label=target_label,
        relinked_substrate_count=organization.relinked_substrate_count,
        relinked_substrates=organization.relinked_substrates,
        source_deleted=organization.source_deleted,
        transferred_alias_count=organization.transferred_alias_count,
        transferred_meta_count=organization.transferred_meta_count,
        unapplied_source_geometry=None,
    )


def apply_merge(
    session: Session,
    request: MergeRequest,
    *,
    reindex: ReindexEntity | None,
    activity: MergeActivity | None = None,
) -> MergeOutcome:
    """Merge ``source`` into ``target``, persist ``merged_into``, queue reindex, and log activity.

    Raises ``ValueError`` for anything the merge guard refuses (missing record, different kinds,
    metadata conflict). The caller commits.
    """
    outcome = _run_merge(session, request)
    record_redirect(
        session,
        stylebook_id=request.stylebook_id,
        entity_type=request.entity_type,
        old_id=outcome.source_id,
        new_id=outcome.target_id,
    )
    if reindex is not None:
        for project_id, entity_id in outcome.relinked_substrates:
            reindex(
                session,
                project_id=project_id,
                entity_type=request.entity_type,
                entity_id=entity_id,
            )
    if activity is not None:
        log_stylebook_activity_safe(
            session,
            stylebook_id=request.stylebook_id,
            actor_type=activity.actor_type,
            actor_user_id=activity.actor_user_id,
            source=activity.source,
            event_type=EVENT_CLEANUP_MERGE,
            entity_type=request.entity_type,
            entity_id=outcome.source_id,
            entity_label=outcome.source_label,
            related_entity_type=request.entity_type,
            related_entity_id=outcome.target_id,
            related_entity_label=outcome.target_label,
            payload_json=dict(activity.payload),
        )
    return outcome
