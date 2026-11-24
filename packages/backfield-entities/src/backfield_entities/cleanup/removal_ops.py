"""Retire, reinstate and delete a canonical, for every entity kind.

The Stylebook app's delete routes and the cleanup API both go through here, so removal behaves the
same for locations, people and organizations. Records still linked to the canonical are released
first: returned to the review queue (`requeue`) or set aside as not needing a canonical (`waive`).
Nothing here commits; the caller owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from backfield_db import BackfieldProject
from backfield_events import (
    record_canonical_deleted,
    record_canonical_updated,
    suppress_canonical_evidence_events,
)
from pydantic import JsonValue
from sqlmodel import Session, col, select

from backfield_entities.activity import (
    EVENT_CANONICAL_DELETED,
    EVENT_CANONICAL_REINSTATED,
    EVENT_CANONICAL_RETIRED,
    ActorType,
    log_stylebook_activity,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED
from backfield_entities.cleanup.alias_ops import touch_canonical
from backfield_entities.cleanup.before_state import RowJson, row_to_json
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.connections.lifecycle import close_open_connections_for_canonical

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

# What to do with records still linked to a canonical that is going away. `refuse` is decided by
# the caller (it stops before any change); the other two are carried out here.
ReleaseDisposition = Literal["requeue", "waive"]
MentionDisposition = Literal["refuse", "requeue", "waive"]

# The reason the Stylebook app has always recorded when a delete returned records to the queue.
DELETED_RELEASE_REASON = "reset_pending_after_canonical_deleted"
RETIRED_RELEASE_REASON = "reset_pending_after_canonical_retired"


@dataclass(frozen=True)
class RemovalActivity:
    """The activity row to write for a removal; leave it out to write none."""

    actor_type: ActorType | str
    actor_user_id: int | None = None
    source: str = "cleanup_api"
    # Extra facts for the row, such as the run, your item id, or the key that made the change.
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RemovalOutcome:
    canonical_id: str
    label: str
    # (project_id, record_id) for each linked record that was released.
    released_records: list[tuple[int, int]] = field(default_factory=list)
    # Those records as they were, so a change can be understood or undone.
    released_before: list[RowJson] = field(default_factory=list)
    connections_closed: int = 0


def _organization_project_ids(session: Session, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def linked_records_for_canonical(
    session: Session, models: CleanupEntityModels, *, organization_id: int, canonical_id: str
) -> list[Any]:
    """The project records linked to a canonical, across the organization's projects."""
    project_ids = _organization_project_ids(session, organization_id)
    if not project_ids:
        return []
    link = models.column(models.substrate, models.substrate_canonical_column)
    return list(
        session.exec(
            select(models.substrate)
            .where(col(models.substrate.project_id).in_(project_ids), link == canonical_id)
            .order_by(models.substrate.id)
        ).all()
    )


def _release_linked_records(
    models: CleanupEntityModels,
    records: list[Any],
    *,
    canonical_id: str,
    disposition: ReleaseDisposition,
    reason_code: str,
    reason_key: str,
    session: Session,
) -> tuple[list[RowJson], list[tuple[int, int]]]:
    status = CANONICAL_LINK_PENDING if disposition == "requeue" else CANONICAL_LINK_WAIVED
    before: list[RowJson] = []
    released: list[tuple[int, int]] = []
    for record in records:
        snapshot = row_to_json(record)
        before.append(
            {
                "project_id": int(record.project_id),
                "id": int(record.id),
                models.substrate_canonical_column: canonical_id,
                "canonical_link_status": snapshot["canonical_link_status"],
                "canonical_review_reasons_json": snapshot["canonical_review_reasons_json"],
            }
        )
        released.append((int(record.project_id), int(record.id)))
        setattr(record, models.substrate_canonical_column, None)
        record.canonical_link_status = status
        record.canonical_review_reasons_json = [{"code": reason_code, reason_key: canonical_id}]
        session.add(record)
    return before, released


def _write_activity(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    *,
    stylebook_id: int,
    event_type: str,
    activity: RemovalActivity | None,
    payload: dict[str, JsonValue],
) -> None:
    if activity is None:
        return
    log_stylebook_activity(
        session,
        stylebook_id=stylebook_id,
        actor_type=activity.actor_type,
        actor_user_id=activity.actor_user_id,
        source=activity.source,
        event_type=event_type,
        entity_type=models.singular,
        entity_id=str(canonical.id),
        entity_label=str(canonical.label),
        payload_json={**payload, **activity.payload},
    )


def retire_canonical(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    *,
    stylebook_id: int,
    organization_id: int,
    disposition: ReleaseDisposition,
    reason_code: str = RETIRED_RELEASE_REASON,
    activity: RemovalActivity | None = None,
) -> RemovalOutcome:
    """Make a canonical inactive, release its linked records, and close its open connections."""
    canonical_id = str(canonical.id)
    outcome = RemovalOutcome(canonical_id=canonical_id, label=str(canonical.label))
    records = linked_records_for_canonical(
        session, models, organization_id=organization_id, canonical_id=canonical_id
    )
    outcome.released_before, outcome.released_records = _release_linked_records(
        models,
        records,
        canonical_id=canonical_id,
        disposition=disposition,
        reason_code=reason_code,
        reason_key="retired_canonical_id",
        session=session,
    )
    outcome.connections_closed = close_open_connections_for_canonical(
        session, entity_type=models.singular, canonical_id=canonical_id
    ).closed_count
    canonical.status = STATUS_INACTIVE
    touch_canonical(canonical)
    session.add(canonical)
    _write_activity(
        session,
        models,
        canonical,
        stylebook_id=stylebook_id,
        event_type=EVENT_CANONICAL_RETIRED,
        activity=activity,
        payload={
            "released_record_count": len(records),
            "release": disposition,
            "connections_closed": outcome.connections_closed,
        },
    )
    record_canonical_updated(
        session,
        stylebook_id=stylebook_id,
        entity_type=models.singular,
        canonical_id=canonical_id,
        label=outcome.label,
    )
    return outcome


def reinstate_canonical(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    *,
    stylebook_id: int,
    activity: RemovalActivity | None = None,
) -> RemovalOutcome:
    """Make a retired canonical active again. Released records and closed connections stay as
    they are."""
    canonical.status = STATUS_ACTIVE
    touch_canonical(canonical)
    session.add(canonical)
    _write_activity(
        session,
        models,
        canonical,
        stylebook_id=stylebook_id,
        event_type=EVENT_CANONICAL_REINSTATED,
        activity=activity,
        payload={},
    )
    record_canonical_updated(
        session,
        stylebook_id=stylebook_id,
        entity_type=models.singular,
        canonical_id=str(canonical.id),
        label=str(canonical.label),
    )
    return RemovalOutcome(canonical_id=str(canonical.id), label=str(canonical.label))


def delete_canonical(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    *,
    stylebook_id: int,
    organization_id: int,
    disposition: ReleaseDisposition = "requeue",
    reason_code: str = DELETED_RELEASE_REASON,
    activity: RemovalActivity | None = None,
    expected_record_ids: list[int] | None = None,
) -> RemovalOutcome:
    """Delete a canonical: release its linked records, emit the deleted event, close its open
    connections, and remove it. Its aliases and metadata go with it.

    Raises ``ValueError`` when ``expected_record_ids`` is given and the linked records changed.
    """
    canonical_id = str(canonical.id)
    # The delete event covers the per-record evidence changes made below.
    suppress_canonical_evidence_events(
        session, entity_type=models.singular, canonical_ids=[canonical_id]
    )
    records = linked_records_for_canonical(
        session, models, organization_id=organization_id, canonical_id=canonical_id
    )
    if expected_record_ids is not None and sorted(int(r.id) for r in records) != sorted(
        expected_record_ids
    ):
        raise ValueError("stale_preview: linked substrates changed")
    outcome = RemovalOutcome(canonical_id=canonical_id, label=str(canonical.label))
    outcome.released_before, outcome.released_records = _release_linked_records(
        models,
        records,
        canonical_id=canonical_id,
        disposition=disposition,
        reason_code=reason_code,
        reason_key="deleted_canonical_id",
        session=session,
    )
    _write_activity(
        session,
        models,
        canonical,
        stylebook_id=stylebook_id,
        event_type=EVENT_CANONICAL_DELETED,
        activity=activity,
        payload={"unlinked_substrate_count": len(records)},
    )
    record_canonical_deleted(
        session,
        stylebook_id=stylebook_id,
        entity_type=models.singular,
        canonical_id=canonical_id,
        label=outcome.label,
    )
    outcome.connections_closed = close_open_connections_for_canonical(
        session, entity_type=models.singular, canonical_id=canonical_id
    ).closed_count
    session.delete(canonical)
    return outcome
