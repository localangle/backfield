"""Leased webhook delivery orchestration (claim → HTTP → fenced terminalize).

The DB transaction that claims a delivery is committed before any HTTP happens,
and completion updates are fenced on the lease token so a stale worker cannot
clobber a reclaimed delivery (same discipline as the S3 ingestion ledger).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backfield_auth.structured_logging import log_event
from backfield_db import (
    BackfieldEvent,
    BackfieldProject,
    BackfieldWebhookEndpoint,
)
from backfield_db.crypto import decrypt_secret
from backfield_events.contracts import envelope_from_event
from backfield_events.cursor import EVENT_RETENTION_DAYS
from backfield_events.delivery import (
    ClaimedDelivery,
    claim_delivery,
    complete_delivery_failure,
    complete_delivery_success,
    find_due_delivery_ids,
)
from backfield_events.signing import build_signature_headers
from backfield_observability.lifecycle import worker_identity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlmodel import Session

from worker.webhooks.sender import WebhookSendResult, send_signed_webhook

logger = logging.getLogger(__name__)

DISPATCH_BATCH_LIMIT = 100


@dataclass(frozen=True)
class PreparedDelivery:
    claim: ClaimedDelivery
    url: str
    body: bytes
    headers: dict[str, str]


def deliver_webhook_delivery(engine: Engine, delivery_id: str) -> str:
    """Attempt one delivery; returns the outcome label for logging/tests."""
    prepared: PreparedDelivery | str
    with Session(engine) as session:
        prepared = _claim_and_prepare(session, delivery_id)
        session.commit()
    if isinstance(prepared, str):
        return prepared

    result = send_signed_webhook(
        url=prepared.url,
        body=prepared.body,
        headers=prepared.headers,
    )

    with Session(engine) as session:
        outcome = _record_result(session, claim=prepared.claim, result=result)
        session.commit()

    _emit_delivery_metrics(result=result, outcome=outcome)
    log_event(
        logger,
        "webhook_delivery_attempt",
        delivery_id=delivery_id,
        outcome=outcome,
        status_code=result.status_code,
        failure_category=result.failure_category,
        duration_ms=result.duration_ms,
    )
    return outcome


def _claim_and_prepare(session: Session, delivery_id: str) -> PreparedDelivery | str:
    claim = claim_delivery(session, delivery_id=delivery_id)
    if claim is None:
        return "not_claimed"

    endpoint = session.get(BackfieldWebhookEndpoint, claim.endpoint_id)
    event = session.get(BackfieldEvent, claim.event_id)
    project = session.get(BackfieldProject, event.project_id) if event else None
    if endpoint is None or event is None or project is None:
        complete_delivery_failure(
            session,
            claim=claim,
            status_code=None,
            failure_category="missing_data",
            failure_summary="Endpoint, event, or project no longer exists",
            duration_ms=0,
            retryable=False,
        )
        return "missing_data"

    envelope = envelope_from_event(event, project_slug=project.slug)
    body = envelope.model_dump_json().encode("utf-8")
    timestamp = str(int(time.time()))
    headers = build_signature_headers(
        secret=decrypt_secret(endpoint.signing_secret_encrypted),
        timestamp=timestamp,
        body=body,
        event_uuid=event.event_uuid,
        delivery_id=claim.delivery_id,
        event_type=event.event_type,
    )
    return PreparedDelivery(
        claim=claim,
        url=decrypt_secret(endpoint.url_encrypted),
        body=body,
        headers=headers,
    )


def _record_result(
    session: Session,
    *,
    claim: ClaimedDelivery,
    result: WebhookSendResult,
) -> str:
    if result.ok:
        applied = complete_delivery_success(
            session,
            claim=claim,
            status_code=int(result.status_code or 0),
            duration_ms=result.duration_ms,
        )
        return "delivered" if applied else "stale"
    return complete_delivery_failure(
        session,
        claim=claim,
        status_code=result.status_code,
        failure_category=result.failure_category or "unknown",
        failure_summary=result.failure_summary,
        duration_ms=result.duration_ms,
        retryable=result.retryable,
        retry_after_seconds=result.retry_after_seconds,
    )


def find_and_deliver_due(engine: Engine, *, limit: int = DISPATCH_BATCH_LIMIT) -> int:
    """Synchronously process due deliveries (recovery path); returns attempts made."""
    with Session(engine) as session:
        due = find_due_delivery_ids(session, limit=limit)
    for delivery_id in due:
        deliver_webhook_delivery(engine, delivery_id)
    return len(due)


def purge_expired_events(engine: Engine, *, now: datetime | None = None) -> int:
    """Delete events past the retention window (deliveries/attempts cascade)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=EVENT_RETENTION_DAYS)
    with Session(engine) as session:
        result = session.exec(
            delete(BackfieldEvent).where(BackfieldEvent.created_at < cutoff)
        )
        session.commit()
        purged = int(result.rowcount or 0)
    if purged:
        log_event(logger, "webhook_events_purged", purged=purged)
    return purged


def _emit_delivery_metrics(*, result: WebhookSendResult, outcome: str) -> None:
    """Low-cardinality delivery metrics; no project/endpoint/URL/error dimensions."""
    identity = worker_identity()
    log_metric(
        "webhook_delivery_attempts_total",
        1,
        identity=identity,
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
    )
    log_metric(
        "webhook_delivery_duration_seconds",
        result.duration_ms / 1000.0,
        identity=identity,
        unit=MetricUnit.SECONDS,
        kind=MetricKind.DISTRIBUTION,
    )
    if not result.ok:
        log_metric(
            "webhook_delivery_failures_total",
            1,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.COUNTER,
        )
    if outcome == "paused":
        log_metric(
            "webhook_endpoints_paused_total",
            1,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.COUNTER,
        )
    if outcome in ("failed", "paused"):
        log_metric(
            "webhook_deliveries_dead_total",
            1,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.COUNTER,
        )
