"""Celery before_task_publish hook: stamp enqueue time for queue age metrics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

PUBLISH_TIMESTAMP_HEADER = "backfield_published_at"


def stamp_task_publish_headers(
    body: Any = None,
    headers: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    """Add a UTC ISO publish timestamp to Celery message headers when missing."""
    del body
    if headers is None:
        return
    if headers.get(PUBLISH_TIMESTAMP_HEADER):
        return
    headers[PUBLISH_TIMESTAMP_HEADER] = datetime.now(UTC).isoformat()


_REGISTERED = False


def register_publish_timestamp_hook() -> None:
    """Connect the publish-timestamp hook (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    from celery.signals import before_task_publish

    before_task_publish.connect(stamp_task_publish_headers, weak=False)
    _REGISTERED = True
