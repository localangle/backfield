"""First-class typed domain events: registry, recorder, and transaction hygiene.

Every webhook/feed event is a :class:`DomainEvent` subclass registered by its
``event_type``. Emission is a single call — ``record_event(session, event)`` —
made inside the same open transaction as the domain mutation, so an event
exists if and only if the mutation commits. The recorder:

- gates on ``webhooks_enabled()``;
- expands the event into one immutable ``BackfieldEvent`` row per
  :class:`EventScope` (stylebook-scoped events fan out to one row per project
  attached to the stylebook);
- drops events whose coalesce key already recorded in this transaction, and
  events explicitly suppressed via :func:`suppress_events` (e.g. a canonical
  merge suppresses the per-link evidence events it would otherwise cascade);
- creates pending deliveries for matching active endpoints;
- stashes :class:`RecordedEvent` results on ``session.info`` so callers can
  drain them once after commit (:func:`pop_recorded_events`) and kick the
  delivery dispatcher.

Session-level bookkeeping is cleared automatically on commit and rollback via
class-level SQLAlchemy listeners, so pooled or long-lived sessions cannot leak
coalesce state across transactions.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from backfield_db import (
    BackfieldEvent,
    BackfieldWebhookDelivery,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
)
from pydantic import BaseModel, Field
from sqlalchemy import event as sa_event
from sqlalchemy import or_
from sqlalchemy.orm import Session as SqlAlchemySession
from sqlmodel import Session, col, select

from backfield_events.config import webhooks_enabled
from backfield_events.recording import (
    DELIVERY_STATE_PENDING,
    ENDPOINT_STATUS_ACTIVE,
    RecordedEvent,
    subscription_matches_outcome,
)

_RECORDED_KEY = "backfield_events.recorded"
_COALESCED_KEY = "backfield_events.coalesced"
_SUPPRESSED_KEY = "backfield_events.suppressed"


@dataclass(frozen=True)
class EventScope:
    """One project-scoped ``backfield_event`` row an event expands into."""

    organization_id: int
    project_id: int
    graph_id: str | None = None
    graph_name: str | None = None
    run_id: str | None = None
    execution_attempt: int | None = None
    article_id: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class DomainEvent(BaseModel):
    """Base class for all recordable events.

    Subclasses set ``event_type`` (which registers them) and ``flow_scoped``,
    and implement :meth:`scopes` and :meth:`payload`.
    """

    #: Public event type string, e.g. ``"agate.run.completed"``.
    event_type: ClassVar[str] = ""
    #: Flow-scoped events match per-flow subscription rows in addition to
    #: all-flows rows; non-flow-scoped events match all-flows rows only.
    flow_scoped: ClassVar[bool] = False

    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls.event_type:
            _REGISTRY[cls.event_type] = cls

    def scopes(self, session: Session) -> Sequence[EventScope]:
        """Project scopes to record; one ``BackfieldEvent`` row per scope."""
        raise NotImplementedError

    def payload(self) -> dict[str, object]:
        """JSON-safe ``data`` payload stored on the event row."""
        raise NotImplementedError

    def outcome(self) -> str | None:
        """Value checked against subscription outcome filters; None skips them."""
        return None

    def coalesce_key(self, scope: EventScope) -> tuple[object, ...] | None:
        """Non-None keys are recorded at most once per transaction."""
        return None

    def suppression_key(self) -> tuple[object, ...] | None:
        """Key matched against :func:`suppress_events` entries; None never matches."""
        return None


_REGISTRY: dict[str, type[DomainEvent]] = {}


def registered_event_types() -> tuple[str, ...]:
    """All registered public event types, sorted for stable validation output."""
    return tuple(sorted(_REGISTRY))


def event_type_is_registered(event_type: str) -> bool:
    return event_type in _REGISTRY


def event_type_is_flow_scoped(event_type: str) -> bool:
    cls = _REGISTRY.get(event_type)
    return bool(cls is not None and cls.flow_scoped)


def record_event(session: Session, event: DomainEvent) -> tuple[RecordedEvent, ...]:
    """Record ``event`` (no commit); returns one ``RecordedEvent`` per scope row.

    The caller owns the transaction and should kick the delivery dispatcher
    only after commit, either with the return value or by draining
    :func:`pop_recorded_events`.
    """
    if not webhooks_enabled():
        return ()

    suppression = event.suppression_key()
    if suppression is not None and suppression in _info_set(session, _SUPPRESSED_KEY):
        return ()

    recorded: list[RecordedEvent] = []
    for scope in event.scopes(session):
        key = event.coalesce_key(scope)
        if key is not None:
            coalesced = _info_set(session, _COALESCED_KEY)
            if key in coalesced:
                continue
            coalesced.add(key)

        row = BackfieldEvent(
            event_type=event.event_type,
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            graph_id=scope.graph_id,
            graph_name=scope.graph_name,
            run_id=scope.run_id,
            execution_attempt=scope.execution_attempt,
            article_id=scope.article_id,
            entity_type=scope.entity_type,
            entity_id=scope.entity_id,
            payload_json=json.dumps(event.payload()),
            occurred_at=event.occurred_at,
            is_test=False,
        )
        session.add(row)
        session.flush()

        delivery_ids: list[str] = []
        for endpoint in _matching_active_endpoints(
            session,
            project_id=scope.project_id,
            event_type=event.event_type,
            graph_id=scope.graph_id if event.flow_scoped else None,
            flow_scoped=event.flow_scoped,
            outcome=event.outcome(),
        ):
            delivery = BackfieldWebhookDelivery(
                event_id=int(row.id or 0),
                endpoint_id=endpoint.id,
                state=DELIVERY_STATE_PENDING,
                next_attempt_at=event.occurred_at,
            )
            session.add(delivery)
            delivery_ids.append(delivery.id)
        session.flush()

        result = RecordedEvent(
            event_id=int(row.id or 0),
            event_uuid=row.event_uuid,
            delivery_ids=tuple(delivery_ids),
        )
        recorded.append(result)
        session.info.setdefault(_RECORDED_KEY, []).append(result)

    return tuple(recorded)


def pop_recorded_events(session: Session) -> tuple[RecordedEvent, ...]:
    """Drain events recorded through this session; call after commit.

    Callers use the result to decide whether to kick the delivery dispatcher;
    the scheduled recovery sweep remains authoritative when the kick is skipped.
    """
    items: list[RecordedEvent] = session.info.pop(_RECORDED_KEY, [])
    return tuple(items)


def suppress_events(session: Session, keys: Iterable[tuple[object, ...]]) -> None:
    """Suppress events whose ``suppression_key`` matches, for this transaction.

    Used by compound operations (e.g. canonical merge) to swallow the finer-
    grained events their internal steps would otherwise emit.
    """
    _info_set(session, _SUPPRESSED_KEY).update(keys)


def _info_set(session: Session, key: str) -> set[tuple[object, ...]]:
    existing = session.info.get(key)
    if existing is None:
        existing = set()
        session.info[key] = existing
    return existing


def _matching_active_endpoints(
    session: Session,
    *,
    project_id: int,
    event_type: str,
    graph_id: str | None,
    flow_scoped: bool,
    outcome: str | None,
) -> list[BackfieldWebhookEndpoint]:
    if flow_scoped and graph_id is not None:
        # Explicit-flow rows for this graph, or all-flows (NULL) rows.
        graph_clause = or_(
            BackfieldWebhookSubscription.graph_id == graph_id,
            col(BackfieldWebhookSubscription.graph_id).is_(None),
        )
    else:
        graph_clause = col(BackfieldWebhookSubscription.graph_id).is_(None)

    rows = session.exec(
        select(BackfieldWebhookEndpoint, BackfieldWebhookSubscription)
        .join(
            BackfieldWebhookSubscription,
            BackfieldWebhookSubscription.endpoint_id == BackfieldWebhookEndpoint.id,
        )
        .where(
            BackfieldWebhookEndpoint.project_id == project_id,
            BackfieldWebhookEndpoint.status == ENDPOINT_STATUS_ACTIVE,
            BackfieldWebhookSubscription.event_type == event_type,
            graph_clause,
        )
    ).all()

    matched: list[BackfieldWebhookEndpoint] = []
    seen: set[str] = set()
    for endpoint, subscription in rows:
        if endpoint.id in seen:
            continue
        if outcome is not None and not subscription_matches_outcome(subscription, outcome):
            continue
        seen.add(endpoint.id)
        matched.append(endpoint)
    return matched


def _clear_transaction_state(session: SqlAlchemySession) -> None:
    session.info.pop(_COALESCED_KEY, None)
    session.info.pop(_SUPPRESSED_KEY, None)


def _clear_all_state(session: SqlAlchemySession) -> None:
    _clear_transaction_state(session)
    session.info.pop(_RECORDED_KEY, None)


# Recorded events survive commit (callers drain them post-commit for the
# dispatcher kick) but coalesce/suppression state must not leak into the next
# transaction; a rollback discards everything.
sa_event.listen(SqlAlchemySession, "after_commit", _clear_transaction_state)
sa_event.listen(SqlAlchemySession, "after_rollback", _clear_all_state)
