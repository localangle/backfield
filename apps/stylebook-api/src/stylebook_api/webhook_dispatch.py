"""Best-effort webhook dispatcher kick after request commit.

Stylebook routes record canonical events through the shared
``backfield_events`` session collector; the ``get_session`` dependency calls
:func:`kick_webhook_dispatch_if_recorded` after the route returns so committed
deliveries start promptly. The scheduled recovery sweep remains authoritative.
"""

from __future__ import annotations

import logging
import os

from backfield_events import pop_recorded_events
from celery import Celery
from sqlmodel import Session

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def kick_webhook_dispatch_if_recorded(session: Session) -> None:
    recorded = pop_recorded_events(session)
    if not any(event.delivery_ids for event in recorded):
        return
    try:
        celery_app.send_task(
            "worker.tasks.dispatch_webhook_deliveries",
            queue=os.environ.get("CELERY_QUEUE", "agate"),
        )
    except Exception:
        logger.warning(
            "Webhook dispatch kick failed; scheduled recovery will deliver",
            exc_info=True,
        )
