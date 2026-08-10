"""Stylebook canonical entity events with per-project fan-out.

Canonicals belong to a stylebook shared by multiple projects, while events and
webhook endpoints are project-scoped, so one canonical change records one
event row in every project attached to the stylebook.

Emission call sites live in the shared ``backfield-entities`` mutation helpers
(and the Stylebook API patch routers) inside the same open transaction as the
mutation. ``evidence.changed`` coalesces per canonical per transaction, and
compound operations (merge, delete) suppress the per-link evidence events
their internal steps would otherwise emit.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from backfield_db import BackfieldProject
from sqlmodel import Session, select

from backfield_events.contracts import (
    CANONICAL_CREATED_EVENT,
    CANONICAL_DELETED_EVENT,
    CANONICAL_EVIDENCE_CHANGED_EVENT,
    CANONICAL_MERGED_EVENT,
    CANONICAL_UPDATED_EVENT,
    CanonicalEntityType,
    CanonicalEventData,
    CanonicalEvidenceChangedData,
    CanonicalMergedData,
)
from backfield_events.events import DomainEvent, EventScope, record_event, suppress_events
from backfield_events.recording import RecordedEvent


class _CanonicalEventBase(DomainEvent):
    #: Canonical events are never flow-scoped; they match all-flows subscriptions only.
    flow_scoped: ClassVar[bool] = False

    stylebook_id: int
    entity_type: CanonicalEntityType
    canonical_id: str

    def scopes(self, session: Session) -> list[EventScope]:
        rows = session.exec(
            select(BackfieldProject.id, BackfieldProject.organization_id).where(
                BackfieldProject.stylebook_id == self.stylebook_id
            )
        ).all()
        return [
            EventScope(
                organization_id=int(organization_id),
                project_id=int(project_id),
                entity_type=self.entity_type,
                entity_id=self.canonical_id,
            )
            for project_id, organization_id in rows
            if project_id is not None
        ]

    def coalesce_key(self, scope: EventScope) -> tuple[object, ...]:
        return (self.event_type, scope.project_id, self.entity_type, self.canonical_id)


class CanonicalCreated(_CanonicalEventBase):
    event_type = CANONICAL_CREATED_EVENT

    data: CanonicalEventData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


class CanonicalUpdated(_CanonicalEventBase):
    event_type = CANONICAL_UPDATED_EVENT

    data: CanonicalEventData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


class CanonicalDeleted(_CanonicalEventBase):
    event_type = CANONICAL_DELETED_EVENT

    data: CanonicalEventData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


class CanonicalMerged(_CanonicalEventBase):
    """Source canonical folded into a target; scope is the retired source ID."""

    event_type = CANONICAL_MERGED_EVENT

    data: CanonicalMergedData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


class CanonicalEvidenceChanged(_CanonicalEventBase):
    """The substrate evidence behind a canonical changed (link/unlink/mentions)."""

    event_type = CANONICAL_EVIDENCE_CHANGED_EVENT

    data: CanonicalEvidenceChangedData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()

    def suppression_key(self) -> tuple[object, ...]:
        return _evidence_suppression_key(self.entity_type, self.canonical_id)


def record_canonical_created(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: CanonicalEntityType,
    canonical_id: str,
    label: str | None,
) -> tuple[RecordedEvent, ...]:
    return record_event(
        session,
        CanonicalCreated(
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            canonical_id=canonical_id,
            data=CanonicalEventData(label=label),
        ),
    )


def record_canonical_updated(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: CanonicalEntityType,
    canonical_id: str,
    label: str | None,
) -> tuple[RecordedEvent, ...]:
    return record_event(
        session,
        CanonicalUpdated(
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            canonical_id=canonical_id,
            data=CanonicalEventData(label=label),
        ),
    )


def record_canonical_deleted(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: CanonicalEntityType,
    canonical_id: str,
    label: str | None,
) -> tuple[RecordedEvent, ...]:
    suppress_canonical_evidence_events(
        session,
        entity_type=entity_type,
        canonical_ids=[canonical_id],
    )
    return record_event(
        session,
        CanonicalDeleted(
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            canonical_id=canonical_id,
            data=CanonicalEventData(label=label),
        ),
    )


def record_canonical_merged(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: CanonicalEntityType,
    source_canonical_id: str,
    target_canonical_id: str,
    label: str | None,
) -> tuple[RecordedEvent, ...]:
    """Record the merge under the retired source ID; suppresses evidence noise."""
    suppress_canonical_evidence_events(
        session,
        entity_type=entity_type,
        canonical_ids=[source_canonical_id, target_canonical_id],
    )
    return record_event(
        session,
        CanonicalMerged(
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            canonical_id=source_canonical_id,
            data=CanonicalMergedData(label=label, merged_into=target_canonical_id),
        ),
    )


def record_canonical_evidence_changed(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: CanonicalEntityType,
    canonical_id: str,
    label: str | None,
    change: str,
) -> tuple[RecordedEvent, ...]:
    return record_event(
        session,
        CanonicalEvidenceChanged(
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            canonical_id=canonical_id,
            data=CanonicalEvidenceChangedData(label=label, change=change),
        ),
    )


def suppress_canonical_evidence_events(
    session: Session,
    *,
    entity_type: CanonicalEntityType,
    canonical_ids: Iterable[str],
) -> None:
    """Swallow evidence events for these canonicals for the rest of the transaction."""
    suppress_events(
        session,
        (_evidence_suppression_key(entity_type, canonical_id) for canonical_id in canonical_ids),
    )


def _evidence_suppression_key(
    entity_type: str,
    canonical_id: str,
) -> tuple[object, ...]:
    return (CANONICAL_EVIDENCE_CHANGED_EVENT, entity_type, canonical_id)
