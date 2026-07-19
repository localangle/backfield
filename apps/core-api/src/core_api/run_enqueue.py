"""Enqueue Agate worker tasks from Core API (mirrors agate-api producer)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from backfield_db import BackfieldPublicIdempotencyRecord
from celery import Celery
from sqlalchemy import and_, column, or_, update
from sqlmodel import Session

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

ENQUEUE_STATE_PENDING = "pending"
ENQUEUE_STATE_PUBLISHING = "publishing"
ENQUEUE_STATE_PUBLISHED = "published"
ENQUEUE_CLAIM_TTL = timedelta(seconds=30)

PublishOutcome = Literal["published", "in_progress", "unavailable"]


def celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def enqueue_worker_task(task_name: str, args: list[Any]) -> None:
    celery_app.send_task(task_name, args=args, queue=celery_queue())


def encode_enqueue_args(args: list[Any]) -> str:
    return json.dumps(args, separators=(",", ":"), ensure_ascii=False)


def decode_enqueue_args(raw: str | None) -> list[Any]:
    if raw is None or not raw.strip():
        raise ValueError("Missing enqueue args on idempotency record")
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Enqueue args must be a JSON array")
    return parsed


def _claim_expired_cutoff(now: datetime) -> datetime:
    return now - ENQUEUE_CLAIM_TTL


def claim_idempotency_enqueue(
    session: Session,
    record_id: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Atomically claim a pending or expired publishing record for broker publish."""
    now = now or datetime.now(UTC)
    expired_before = _claim_expired_cutoff(now)
    result = session.execute(
        update(BackfieldPublicIdempotencyRecord)
        .where(
            BackfieldPublicIdempotencyRecord.id == record_id,
            or_(
                BackfieldPublicIdempotencyRecord.enqueue_state == ENQUEUE_STATE_PENDING,
                and_(
                    BackfieldPublicIdempotencyRecord.enqueue_state == ENQUEUE_STATE_PUBLISHING,
                    or_(
                        BackfieldPublicIdempotencyRecord.enqueue_claimed_at.is_(None),
                        BackfieldPublicIdempotencyRecord.enqueue_claimed_at <= expired_before,
                    ),
                ),
            ),
        )
        .values(
            enqueue_state=ENQUEUE_STATE_PUBLISHING,
            enqueue_claimed_at=now,
            enqueue_attempt_count=column("enqueue_attempt_count") + 1,
            enqueue_last_error=None,
        )
    )
    session.commit()
    return int(result.rowcount or 0) == 1


def mark_idempotency_published(
    session: Session,
    record_id: int,
    *,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    session.execute(
        update(BackfieldPublicIdempotencyRecord)
        .where(
            BackfieldPublicIdempotencyRecord.id == record_id,
            BackfieldPublicIdempotencyRecord.enqueue_state == ENQUEUE_STATE_PUBLISHING,
        )
        .values(
            enqueue_state=ENQUEUE_STATE_PUBLISHED,
            enqueued_at=now,
            enqueue_last_error=None,
        )
    )
    session.commit()


def release_idempotency_enqueue_claim(
    session: Session,
    record_id: int,
    *,
    error: str,
) -> None:
    session.execute(
        update(BackfieldPublicIdempotencyRecord)
        .where(
            BackfieldPublicIdempotencyRecord.id == record_id,
            BackfieldPublicIdempotencyRecord.enqueue_state == ENQUEUE_STATE_PUBLISHING,
        )
        .values(
            enqueue_state=ENQUEUE_STATE_PENDING,
            enqueue_claimed_at=None,
            enqueue_last_error=error[:2000],
        )
    )
    session.commit()


def publish_idempotency_enqueue(
    session: Session,
    record: BackfieldPublicIdempotencyRecord,
    *,
    enqueue_task: Any = enqueue_worker_task,
    now: datetime | None = None,
) -> PublishOutcome:
    """Publish the stored Celery descriptor for a keyed public run.

    Returns:
        published: task was sent (or already published)
        in_progress: another request holds a fresh publishing claim
        unavailable: broker publish failed; record returned to pending
    """
    now = now or datetime.now(UTC)
    if record.id is None:
        raise RuntimeError("Idempotency record id missing")
    if record.enqueue_state == ENQUEUE_STATE_PUBLISHED:
        return "published"

    claimed = claim_idempotency_enqueue(session, int(record.id), now=now)
    session.refresh(record)
    if not claimed:
        if record.enqueue_state == ENQUEUE_STATE_PUBLISHED:
            return "published"
        return "in_progress"

    task_name = (record.enqueue_task_name or "").strip()
    try:
        args = decode_enqueue_args(record.enqueue_args_json)
        if not task_name:
            raise ValueError("Missing enqueue task name on idempotency record")
        enqueue_task(task_name, args)
    except Exception as exc:
        release_idempotency_enqueue_claim(session, int(record.id), error=str(exc))
        session.refresh(record)
        return "unavailable"

    mark_idempotency_published(session, int(record.id), now=now)
    session.refresh(record)
    return "published"
