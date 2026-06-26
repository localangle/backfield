"""Celery task hooks for structured worker logging."""

from __future__ import annotations

import logging

from backfield_auth.log_context import (
    LogContextReset,
    bind_log_context,
    clear_log_context,
    reset_log_context,
)
from backfield_auth.structured_logging import configure_structured_logging, log_event
from celery.signals import task_failure, task_postrun, task_prerun

logger = logging.getLogger("backfield.worker.task")

_RUN_ID_TASKS = frozenset(
    {
        "worker.tasks.execute_agate_run",
        "worker.tasks.execute_s3_batch_setup",
        "worker.tasks.execute_run_replay_setup",
        "worker.tasks.finalize_s3_parent_run",
    }
)

_CONTEXT_RESETS: dict[str, LogContextReset] = {}


def _infer_run_id(task_name: str | None, args: tuple[object, ...]) -> str | None:
    if task_name in _RUN_ID_TASKS and args:
        return str(args[0])
    return None


@task_prerun.connect
def _log_task_prerun(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    **_: object,
) -> None:
    configure_structured_logging("worker")
    task_name = task.name if task is not None else None
    run_id = _infer_run_id(task_name, tuple(args or ()))
    reset = bind_log_context(job_id=task_id, run_id=run_id)
    if task_id:
        _CONTEXT_RESETS[task_id] = reset
    log_event(logger, "task_start", task=task_name)


@task_postrun.connect
def _log_task_postrun(
    sender=None,
    task_id=None,
    task=None,
    state=None,
    **_: object,
) -> None:
    task_name = task.name if task is not None else None
    log_event(logger, "task_end", task=task_name, state=state)
    reset = _CONTEXT_RESETS.pop(task_id, None) if task_id else None
    reset_log_context(reset)
    clear_log_context()


@task_failure.connect
def _log_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    **_: object,
) -> None:
    task_name = sender.name if sender is not None else None
    log_event(
        logger,
        "task_failure",
        level=logging.ERROR,
        task=task_name,
        job_id=task_id,
        error=str(exception) if exception is not None else None,
    )
