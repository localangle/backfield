"""Leased claim / terminalize bookkeeping for webhook deliveries.

Follows the S3 ingestion ledger pattern: claims are optimistic single-row
updates guarded by state and lease expiry, and completions are fenced on the
lease token so stale workers cannot clobber a reclaimed delivery.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backfield_db import (
    BackfieldWebhookDelivery,
    BackfieldWebhookDeliveryAttempt,
    BackfieldWebhookEndpoint,
)
from sqlmodel import Session, select, update

from backfield_events.recording import (
    DELIVERY_STATE_DELIVERING,
    DELIVERY_STATE_FAILED,
    DELIVERY_STATE_PENDING,
    ENDPOINT_STATUS_ACTIVE,
    ENDPOINT_STATUS_PAUSED,
)

RETRY_WINDOW = timedelta(hours=24)
DEFAULT_LEASE_DURATION = timedelta(minutes=5)
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 3600

#: HTTP statuses (beyond 5xx) that are retried; other 4xx responses terminalize.
RETRYABLE_STATUS_CODES = frozenset({408, 429})

FAILURE_SUMMARY_MAX_LENGTH = 300

PAUSE_REASON_RETRIES_EXHAUSTED = "delivery_retries_exhausted"


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: str
    lease_token: str
    event_id: int
    endpoint_id: str
    attempt_number: int


def status_code_is_retryable(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or 500 <= status_code <= 599


def find_due_delivery_ids(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> list[str]:
    """Deliveries that are due and claimable for active endpoints."""
    current = now or datetime.now(UTC)
    rows = session.exec(
        select(BackfieldWebhookDelivery.id)
        .join(
            BackfieldWebhookEndpoint,
            BackfieldWebhookEndpoint.id == BackfieldWebhookDelivery.endpoint_id,
        )
        .where(
            BackfieldWebhookDelivery.state.in_(  # type: ignore[attr-defined]
                [DELIVERY_STATE_PENDING, DELIVERY_STATE_DELIVERING]
            ),
            BackfieldWebhookDelivery.next_attempt_at <= current,
            (BackfieldWebhookDelivery.lease_expires_at.is_(None))  # type: ignore[union-attr]
            | (BackfieldWebhookDelivery.lease_expires_at <= current),
            BackfieldWebhookEndpoint.status == ENDPOINT_STATUS_ACTIVE,
        )
        .order_by(BackfieldWebhookDelivery.next_attempt_at)
        .limit(limit)
    ).all()
    return [str(row) for row in rows]


def claim_delivery(
    session: Session,
    *,
    delivery_id: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_LEASE_DURATION,
) -> ClaimedDelivery | None:
    """Atomically claim one due delivery; None when it is not claimable."""
    claimed_at = now or datetime.now(UTC)
    lease_token = str(uuid4())

    delivery = session.get(BackfieldWebhookDelivery, delivery_id)
    if delivery is None:
        return None
    if delivery.state not in (DELIVERY_STATE_PENDING, DELIVERY_STATE_DELIVERING):
        return None

    endpoint = session.get(BackfieldWebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or endpoint.status != ENDPOINT_STATUS_ACTIVE:
        return None

    observed_state = delivery.state
    result = session.execute(
        update(BackfieldWebhookDelivery)
        .where(
            BackfieldWebhookDelivery.id == delivery_id,
            BackfieldWebhookDelivery.state == observed_state,
            BackfieldWebhookDelivery.next_attempt_at <= claimed_at,
            (BackfieldWebhookDelivery.lease_expires_at.is_(None))
            | (BackfieldWebhookDelivery.lease_expires_at <= claimed_at),
        )
        .values(
            state=DELIVERY_STATE_DELIVERING,
            lease_token=lease_token,
            lease_expires_at=claimed_at + lease_duration,
            attempt_count=int(delivery.attempt_count or 0) + 1,
            first_attempted_at=delivery.first_attempted_at or claimed_at,
            updated_at=claimed_at,
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        return None
    return ClaimedDelivery(
        delivery_id=delivery_id,
        lease_token=lease_token,
        event_id=delivery.event_id,
        endpoint_id=delivery.endpoint_id,
        attempt_number=int(delivery.attempt_count or 0) + 1,
    )


def complete_delivery_success(
    session: Session,
    *,
    claim: ClaimedDelivery,
    status_code: int,
    duration_ms: int | None,
    now: datetime | None = None,
) -> bool:
    """Terminalize a claimed delivery as delivered; False when the lease is stale."""
    completed_at = now or datetime.now(UTC)
    result = session.execute(
        update(BackfieldWebhookDelivery)
        .where(
            BackfieldWebhookDelivery.id == claim.delivery_id,
            BackfieldWebhookDelivery.lease_token == claim.lease_token,
            BackfieldWebhookDelivery.state == DELIVERY_STATE_DELIVERING,
        )
        .values(
            state="delivered",
            delivered_at=completed_at,
            last_status_code=status_code,
            failure_category=None,
            failure_summary=None,
            lease_token=None,
            lease_expires_at=None,
            updated_at=completed_at,
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        return False
    _append_attempt(
        session,
        claim=claim,
        attempted_at=completed_at,
        status_code=status_code,
        failure_category=None,
        failure_summary=None,
        duration_ms=duration_ms,
    )
    session.execute(
        update(BackfieldWebhookEndpoint)
        .where(BackfieldWebhookEndpoint.id == claim.endpoint_id)
        .values(last_success_at=completed_at, updated_at=completed_at)
        .execution_options(synchronize_session=False)
    )
    return True


def complete_delivery_failure(
    session: Session,
    *,
    claim: ClaimedDelivery,
    status_code: int | None,
    failure_category: str,
    failure_summary: str | None,
    duration_ms: int | None,
    retryable: bool,
    retry_after_seconds: int | None = None,
    now: datetime | None = None,
) -> str:
    """Record a failed attempt; returns "retry_scheduled", "failed", "paused", or "stale".

    "paused" means this delivery exhausted the 24-hour retry window and the
    endpoint was auto-paused.
    """
    completed_at = now or datetime.now(UTC)
    delivery = session.get(BackfieldWebhookDelivery, claim.delivery_id)
    if (
        delivery is None
        or delivery.lease_token != claim.lease_token
        or delivery.state != DELIVERY_STATE_DELIVERING
    ):
        return "stale"

    summary = (failure_summary or "")[:FAILURE_SUMMARY_MAX_LENGTH] or None
    _append_attempt(
        session,
        claim=claim,
        attempted_at=completed_at,
        status_code=status_code,
        failure_category=failure_category,
        failure_summary=summary,
        duration_ms=duration_ms,
    )
    session.execute(
        update(BackfieldWebhookEndpoint)
        .where(BackfieldWebhookEndpoint.id == claim.endpoint_id)
        .values(last_failure_at=completed_at, updated_at=completed_at)
        .execution_options(synchronize_session=False)
    )

    next_attempt_at: datetime | None = None
    if retryable:
        next_attempt_at = _next_attempt_time(
            attempt_number=claim.attempt_number,
            retry_after_seconds=retry_after_seconds,
            now=completed_at,
        )
        window_start = delivery.first_attempted_at or delivery.created_at
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=UTC)
        if next_attempt_at > window_start + RETRY_WINDOW:
            next_attempt_at = None

    if next_attempt_at is not None:
        _finish_failure(
            session,
            claim=claim,
            state=DELIVERY_STATE_PENDING,
            next_attempt_at=next_attempt_at,
            status_code=status_code,
            failure_category=failure_category,
            failure_summary=summary,
            completed_at=completed_at,
        )
        return "retry_scheduled"

    _finish_failure(
        session,
        claim=claim,
        state=DELIVERY_STATE_FAILED,
        next_attempt_at=completed_at,
        status_code=status_code,
        failure_category=failure_category,
        failure_summary=summary,
        completed_at=completed_at,
    )
    if retryable and not delivery.is_test:
        pause_endpoint(
            session,
            endpoint_id=claim.endpoint_id,
            reason=PAUSE_REASON_RETRIES_EXHAUSTED,
            now=completed_at,
        )
        return "paused"
    return "failed"


def pause_endpoint(
    session: Session,
    *,
    endpoint_id: str,
    reason: str,
    now: datetime | None = None,
) -> None:
    paused_at = now or datetime.now(UTC)
    session.execute(
        update(BackfieldWebhookEndpoint)
        .where(
            BackfieldWebhookEndpoint.id == endpoint_id,
            BackfieldWebhookEndpoint.status == ENDPOINT_STATUS_ACTIVE,
        )
        .values(
            status=ENDPOINT_STATUS_PAUSED,
            paused_at=paused_at,
            pause_reason=reason,
            updated_at=paused_at,
        )
        .execution_options(synchronize_session=False)
    )


def _finish_failure(
    session: Session,
    *,
    claim: ClaimedDelivery,
    state: str,
    next_attempt_at: datetime,
    status_code: int | None,
    failure_category: str,
    failure_summary: str | None,
    completed_at: datetime,
) -> None:
    session.execute(
        update(BackfieldWebhookDelivery)
        .where(
            BackfieldWebhookDelivery.id == claim.delivery_id,
            BackfieldWebhookDelivery.lease_token == claim.lease_token,
            BackfieldWebhookDelivery.state == DELIVERY_STATE_DELIVERING,
        )
        .values(
            state=state,
            next_attempt_at=next_attempt_at,
            last_status_code=status_code,
            failure_category=failure_category,
            failure_summary=failure_summary,
            lease_token=None,
            lease_expires_at=None,
            updated_at=completed_at,
        )
        .execution_options(synchronize_session=False)
    )


def _append_attempt(
    session: Session,
    *,
    claim: ClaimedDelivery,
    attempted_at: datetime,
    status_code: int | None,
    failure_category: str | None,
    failure_summary: str | None,
    duration_ms: int | None,
) -> None:
    session.add(
        BackfieldWebhookDeliveryAttempt(
            delivery_id=claim.delivery_id,
            attempt_number=claim.attempt_number,
            attempted_at=attempted_at,
            status_code=status_code,
            failure_category=failure_category,
            failure_summary=failure_summary,
            duration_ms=duration_ms,
        )
    )


def _next_attempt_time(
    *,
    attempt_number: int,
    retry_after_seconds: int | None,
    now: datetime,
) -> datetime:
    backoff = min(
        BASE_BACKOFF_SECONDS * (2 ** max(attempt_number - 1, 0)),
        MAX_BACKOFF_SECONDS,
    )
    jittered = backoff * random.uniform(0.8, 1.2)
    if retry_after_seconds is not None:
        bounded_retry_after = min(max(retry_after_seconds, 0), MAX_BACKOFF_SECONDS)
        jittered = max(jittered, float(bounded_retry_after))
    return now + timedelta(seconds=jittered)
