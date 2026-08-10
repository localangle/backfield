"""Atomic event recording plus webhook delivery fan-out.

``record_run_completed_event`` must be called inside the same transaction that
writes the run's terminal state so an event exists if and only if the terminal
transition commits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from backfield_db import (
    AgateGraph,
    AgateRun,
    BackfieldEvent,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
)
from sqlmodel import Session, select

from backfield_events.config import webhooks_enabled
from backfield_events.contracts import (
    RUN_COMPLETED_EVENT,
    CompletionReason,
    RunCompletedCounts,
    RunCompletedData,
    RunOutcome,
)

ENDPOINT_STATUS_PENDING = "pending"
ENDPOINT_STATUS_ACTIVE = "active"
ENDPOINT_STATUS_PAUSED = "paused"
ENDPOINT_STATUS_DISABLED = "disabled"

DELIVERY_STATE_PENDING = "pending"
DELIVERY_STATE_DELIVERING = "delivering"
DELIVERY_STATE_DELIVERED = "delivered"
DELIVERY_STATE_FAILED = "failed"


@dataclass(frozen=True)
class RecordedEvent:
    event_id: int
    event_uuid: str
    delivery_ids: tuple[str, ...]


def record_run_completed_event(
    session: Session,
    *,
    run: AgateRun,
    graph: AgateGraph,
    project: BackfieldProject,
    outcome: RunOutcome,
    completion_reason: CompletionReason,
    failure_category: str | None,
    counts: RunCompletedCounts,
    article_count: int,
    occurred_at: datetime | None = None,
) -> RecordedEvent | None:
    """Insert the immutable event and matching endpoint deliveries (no commit).

    Returns None when webhooks are disabled for this deployment. The caller owns
    the transaction and should kick the delivery dispatcher only after commit.
    """
    if not webhooks_enabled():
        return None

    when = occurred_at or datetime.now(UTC)
    data = RunCompletedData(
        outcome=outcome,
        completion_reason=completion_reason,
        failure_category=failure_category,
        counts=counts,
        article_count=article_count,
    )
    event = BackfieldEvent(
        event_type=RUN_COMPLETED_EVENT,
        organization_id=project.organization_id,
        project_id=int(project.id or 0),
        graph_id=graph.id,
        graph_name=graph.name,
        run_id=run.id,
        execution_attempt=run.execution_attempt,
        payload_json=json.dumps(data.model_dump()),
        occurred_at=when,
        is_test=False,
    )
    session.add(event)
    session.flush()

    delivery_ids: list[str] = []
    for endpoint in _matching_active_endpoints(
        session,
        project_id=int(project.id or 0),
        graph_id=graph.id,
        outcome=outcome,
    ):
        delivery = BackfieldWebhookDelivery(
            event_id=int(event.id or 0),
            endpoint_id=endpoint.id,
            state=DELIVERY_STATE_PENDING,
            next_attempt_at=when,
        )
        session.add(delivery)
        delivery_ids.append(delivery.id)
    session.flush()

    return RecordedEvent(
        event_id=int(event.id or 0),
        event_uuid=event.event_uuid,
        delivery_ids=tuple(delivery_ids),
    )


def _matching_active_endpoints(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    outcome: RunOutcome,
) -> list[BackfieldWebhookEndpoint]:
    rows = session.exec(
        select(BackfieldWebhookEndpoint, BackfieldWebhookSubscription)
        .join(
            BackfieldWebhookSubscription,
            BackfieldWebhookSubscription.endpoint_id == BackfieldWebhookEndpoint.id,
        )
        .where(
            BackfieldWebhookEndpoint.project_id == project_id,
            BackfieldWebhookEndpoint.status == ENDPOINT_STATUS_ACTIVE,
            BackfieldWebhookSubscription.event_type == RUN_COMPLETED_EVENT,
            BackfieldWebhookSubscription.graph_id == graph_id,
        )
    ).all()

    matched: list[BackfieldWebhookEndpoint] = []
    seen: set[str] = set()
    for endpoint, subscription in rows:
        if endpoint.id in seen:
            continue
        if not subscription_matches_outcome(subscription, outcome):
            continue
        seen.add(endpoint.id)
        matched.append(endpoint)
    return matched


def subscription_matches_outcome(
    subscription: BackfieldWebhookSubscription,
    outcome: str,
) -> bool:
    """NULL outcome filter means all outcomes; otherwise a JSON array of outcomes."""
    if not subscription.outcomes_json:
        return True
    try:
        outcomes = json.loads(subscription.outcomes_json)
    except ValueError:
        return True
    if not isinstance(outcomes, list) or not outcomes:
        return True
    return outcome in {str(item) for item in outcomes}
