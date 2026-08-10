"""One-shot webhook recovery and retention pass for scheduled invocation.

Run once per invocation (cloud should schedule every ~60s, mirroring the
metrics collector pattern in docs/OBSERVABILITY.md)::

    python -m worker.webhook_maintenance

Claims and sends due deliveries synchronously (recovering anything the
best-effort post-commit Celery kick missed), purges events past the 90-day
retention window, and emits pending-age gauges. Never enqueued through Celery.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

from backfield_auth.structured_logging import configure_structured_logging, log_event
from backfield_db import BackfieldWebhookDelivery
from backfield_db.session import get_engine
from backfield_events.config import webhooks_enabled
from backfield_observability.identity import read_runtime_identity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric
from sqlalchemy import func
from sqlmodel import Session, col, select

from worker.webhooks.delivery import find_and_deliver_due, purge_expired_events

logger = logging.getLogger("backfield.webhook_maintenance")


def _emit_pending_gauges(engine) -> None:
    identity = read_runtime_identity("worker")
    now = datetime.now(UTC)
    with Session(engine) as session:
        pending_count = int(
            session.exec(
                select(func.count())
                .select_from(BackfieldWebhookDelivery)
                .where(col(BackfieldWebhookDelivery.state).in_(["pending", "delivering"]))
            ).one()
        )
        oldest_created = session.exec(
            select(func.min(BackfieldWebhookDelivery.created_at)).where(
                col(BackfieldWebhookDelivery.state).in_(["pending", "delivering"])
            )
        ).one()
    log_metric(
        "webhook_deliveries_pending",
        pending_count,
        identity=identity,
        unit=MetricUnit.COUNT,
        kind=MetricKind.GAUGE,
    )
    if oldest_created is not None:
        oldest = oldest_created if oldest_created.tzinfo else oldest_created.replace(tzinfo=UTC)
        log_metric(
            "webhook_deliveries_pending_age_seconds",
            max((now - oldest).total_seconds(), 0.0),
            identity=identity,
            unit=MetricUnit.SECONDS,
            kind=MetricKind.GAUGE,
        )


def run_webhook_maintenance() -> int:
    """One recovery + retention pass; returns a process exit code."""
    if not webhooks_enabled():
        log_event(logger, "webhook_maintenance_skipped", reason="webhooks_disabled")
        return 0
    engine = get_engine()
    delivered = find_and_deliver_due(engine)
    purged = purge_expired_events(engine)
    _emit_pending_gauges(engine)
    log_event(
        logger,
        "webhook_maintenance_completed",
        due_processed=delivered,
        events_purged=purged,
    )
    return 0


if __name__ == "__main__":
    configure_structured_logging("worker")
    sys.exit(run_webhook_maintenance())
