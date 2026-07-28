"""Read-only queue/run metrics collector for Backfield Cloud schedules.

Run once per invocation (cloud should schedule every ~60s)::

    python -m worker.metrics_collector

Requires ``BACKFIELD_CLIENT``, ``REDIS_URL`` / Celery queue env, and DB URL.
Uses Service=worker. Never enqueued through Celery.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from backfield_auth.structured_logging import configure_structured_logging, log_event
from backfield_observability.celery_publish import PUBLISH_TIMESTAMP_HEADER
from backfield_observability.identity import read_runtime_identity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric
from sqlmodel import Session, col, select

logger = logging.getLogger("backfield.metrics_collector")


def _queue_name() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def _redis_url() -> str:
    return str(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))


def _decode_publish_timestamp(raw: Any) -> datetime | None:
    """Extract publish timestamp from a Celery Redis list payload."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict):
            return None
        headers = payload.get("headers") or {}
        if not isinstance(headers, dict):
            return None
        stamp = headers.get(PUBLISH_TIMESTAMP_HEADER)
        if not stamp:
            return None
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except Exception:
        return None


def collect_queue_metrics(*, redis_client: Any, queue: str) -> tuple[int | None, float | None]:
    """Return ``(depth, oldest_age_seconds)``; None means omit that gauge."""
    try:
        depth = int(redis_client.llen(queue))
    except Exception:
        log_event(logger, "collector_redis_error", level=logging.ERROR, queue=queue)
        return None, None

    if depth <= 0:
        return 0, 0.0

    try:
        oldest_raw = redis_client.lindex(queue, -1)
    except Exception:
        log_event(logger, "collector_redis_error", level=logging.ERROR, queue=queue)
        return depth, None

    published = _decode_publish_timestamp(oldest_raw)
    if published is None:
        # Unknown age must not be reported as zero.
        log_event(logger, "collector_queue_age_unknown", level=logging.WARNING, queue=queue)
        return depth, None
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    age = max(0.0, (datetime.now(UTC) - published).total_seconds())
    return depth, age


def collect_runs_active(*, session: Session) -> int | None:
    try:
        from backfield_db import AgateRun

        rows = session.exec(
            select(AgateRun).where(col(AgateRun.status).in_(["pending", "running"]))
        ).all()
        return len(list(rows))
    except Exception:
        log_event(logger, "collector_db_error", level=logging.ERROR)
        return None


def run_once() -> int:
    configure_structured_logging("worker")
    identity = read_runtime_identity("worker")
    if identity.client is None:
        log_event(
            logger,
            "collector_skipped_missing_client",
            level=logging.WARNING,
            message="BACKFIELD_CLIENT is required to emit collector metrics",
        )
        return 1

    queue = _queue_name()
    try:
        import redis

        redis_client = redis.Redis.from_url(_redis_url(), decode_responses=False)
        redis_client.ping()
    except Exception:
        log_event(logger, "collector_redis_error", level=logging.ERROR)
        redis_client = None
        depth, oldest_age = None, None
    else:
        depth, oldest_age = collect_queue_metrics(redis_client=redis_client, queue=queue)

    if depth is not None:
        log_metric(
            "queue_depth",
            depth,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.GAUGE,
        )
    if oldest_age is not None:
        log_metric(
            "queue_oldest_age_seconds",
            oldest_age,
            identity=identity,
            unit=MetricUnit.SECONDS,
            kind=MetricKind.GAUGE,
        )

    try:
        from backfield_db.session import get_engine

        with Session(get_engine()) as session:
            active = collect_runs_active(session=session)
    except Exception:
        log_event(logger, "collector_db_error", level=logging.ERROR)
        active = None

    if active is not None:
        log_metric(
            "runs_active",
            active,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.GAUGE,
        )

    log_event(
        logger,
        "collector_pass",
        queue=queue,
        queue_depth=depth,
        queue_oldest_age_seconds=oldest_age,
        runs_active=active,
    )
    return 0


def main() -> None:
    raise SystemExit(run_once())


if __name__ == "__main__":
    main()
