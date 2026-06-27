"""Celery worker for Agate runs."""

from worker import celery_logging as _celery_logging  # noqa: F401 — register Celery signal hooks
