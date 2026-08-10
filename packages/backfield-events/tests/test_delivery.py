"""Delivery claim, retry, fencing, and auto-pause tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backfield_db import (
    BackfieldWebhookDelivery,
    BackfieldWebhookDeliveryAttempt,
    BackfieldWebhookEndpoint,
)
from backfield_events.delivery import (
    claim_delivery,
    complete_delivery_failure,
    complete_delivery_success,
    find_due_delivery_ids,
    status_code_is_retryable,
)
from backfield_events.run_events import record_run_terminal_event
from events_test_helpers import Tenancy, make_endpoint, make_run
from sqlmodel import Session, select


def _make_delivery(session: Session, tenancy: Tenancy) -> BackfieldWebhookDelivery:
    make_endpoint(session, tenancy.project, tenancy.graph)
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"
    recorded = record_run_terminal_event(session, run)
    session.commit()
    assert recorded is not None and len(recorded.delivery_ids) == 1
    return session.get(BackfieldWebhookDelivery, recorded.delivery_ids[0])


def test_retry_classification() -> None:
    assert status_code_is_retryable(500)
    assert status_code_is_retryable(503)
    assert status_code_is_retryable(408)
    assert status_code_is_retryable(429)
    assert not status_code_is_retryable(400)
    assert not status_code_is_retryable(401)
    assert not status_code_is_retryable(404)
    assert not status_code_is_retryable(410)


def test_claim_is_exclusive_until_lease_expiry(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    now = datetime.now(UTC)

    first = claim_delivery(session, delivery_id=delivery.id, now=now)
    session.commit()
    assert first is not None
    assert first.attempt_number == 1

    # Second concurrent claim fails while the lease is live.
    assert claim_delivery(session, delivery_id=delivery.id, now=now) is None

    # After lease expiry the delivery is reclaimable with a new token.
    later = now + timedelta(minutes=10)
    second = claim_delivery(session, delivery_id=delivery.id, now=later)
    session.commit()
    assert second is not None
    assert second.lease_token != first.lease_token
    assert second.attempt_number == 2


def test_stale_lease_token_cannot_complete(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    now = datetime.now(UTC)
    stale = claim_delivery(session, delivery_id=delivery.id, now=now)
    session.commit()
    fresh = claim_delivery(session, delivery_id=delivery.id, now=now + timedelta(minutes=10))
    session.commit()
    assert stale is not None and fresh is not None

    assert not complete_delivery_success(session, claim=stale, status_code=200, duration_ms=5)
    assert (
        complete_delivery_failure(
            session,
            claim=stale,
            status_code=500,
            failure_category="http_5xx",
            failure_summary="HTTP 500",
            duration_ms=5,
            retryable=True,
        )
        == "stale"
    )
    assert complete_delivery_success(session, claim=fresh, status_code=200, duration_ms=5)
    session.commit()

    refreshed = session.get(BackfieldWebhookDelivery, delivery.id)
    assert refreshed.state == "delivered"


def test_retryable_failure_schedules_backoff(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    now = datetime.now(UTC)
    claim = claim_delivery(session, delivery_id=delivery.id, now=now)
    session.commit()
    outcome = complete_delivery_failure(
        session,
        claim=claim,
        status_code=503,
        failure_category="http_5xx",
        failure_summary="HTTP 503",
        duration_ms=5,
        retryable=True,
        now=now,
    )
    session.commit()
    assert outcome == "retry_scheduled"
    refreshed = session.get(BackfieldWebhookDelivery, delivery.id)
    assert refreshed.state == "pending"
    next_at = refreshed.next_attempt_at.replace(tzinfo=UTC)
    assert next_at > now
    attempts = session.exec(select(BackfieldWebhookDeliveryAttempt)).all()
    assert len(attempts) == 1
    assert attempts[0].failure_category == "http_5xx"


def test_permanent_4xx_terminalizes_without_pausing(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    now = datetime.now(UTC)
    claim = claim_delivery(session, delivery_id=delivery.id, now=now)
    session.commit()
    outcome = complete_delivery_failure(
        session,
        claim=claim,
        status_code=404,
        failure_category="http_4xx",
        failure_summary="HTTP 404",
        duration_ms=5,
        retryable=False,
        now=now,
    )
    session.commit()
    assert outcome == "failed"
    refreshed = session.get(BackfieldWebhookDelivery, delivery.id)
    assert refreshed.state == "failed"
    endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
    assert endpoint.status == "active"


def test_retry_window_exhaustion_pauses_endpoint(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    start = datetime.now(UTC)
    claim = claim_delivery(session, delivery_id=delivery.id, now=start)
    session.commit()

    # A retryable failure 25 hours after the first attempt exhausts the window.
    late = start + timedelta(hours=25)
    outcome = complete_delivery_failure(
        session,
        claim=claim,
        status_code=500,
        failure_category="http_5xx",
        failure_summary="HTTP 500",
        duration_ms=5,
        retryable=True,
        now=late,
    )
    session.commit()
    assert outcome == "paused"
    refreshed = session.get(BackfieldWebhookDelivery, delivery.id)
    assert refreshed.state == "failed"
    endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
    assert endpoint.status == "paused"
    assert endpoint.pause_reason == "delivery_retries_exhausted"

    # Paused endpoints are excluded from the due sweep.
    assert find_due_delivery_ids(session, now=late + timedelta(hours=1)) == []


def test_due_sweep_finds_pending_and_expired_leases(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    delivery = _make_delivery(session, tenancy)
    now = datetime.now(UTC)
    assert find_due_delivery_ids(session, now=now) == [delivery.id]

    claim_delivery(session, delivery_id=delivery.id, now=now)
    session.commit()
    # Leased and not yet due again.
    assert find_due_delivery_ids(session, now=now) == []
    # Lease expired: shows up again for recovery.
    assert find_due_delivery_ids(session, now=now + timedelta(minutes=10)) == [delivery.id]
