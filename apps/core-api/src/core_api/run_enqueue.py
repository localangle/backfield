"""Enqueue Agate worker tasks from Core API (mirrors agate-api producer)."""

from __future__ import annotations

import os
from typing import Any

from celery import Celery

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def enqueue_worker_task(task_name: str, args: list[Any]) -> None:
    celery_app.send_task(task_name, args=args, queue=celery_queue())
