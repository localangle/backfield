"""Parallel execution helpers for session-free LLM calls during DBOutput persist."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import TypeVar

from sqlmodel import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")


def canonical_adjudication_max_concurrent() -> int:
    raw = os.getenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", "8")
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def commit_session_before_session_free_llm(session: Session) -> None:
    """Release row locks before parallel LLM work that can take tens of seconds."""
    session.commit()
    logger.debug("Committed DBOutput persist transaction before session-free LLM batch")


def run_callables_parallel(
    tasks: Sequence[Callable[[], T]],
    *,
    max_workers: int,
) -> list[T]:
    """Run callables in order; use a thread pool when max_workers > 1 and len(tasks) > 1."""
    if not tasks:
        return []
    if max_workers <= 1 or len(tasks) <= 1:
        return [task() for task in tasks]

    workers = min(max_workers, len(tasks))
    ordered: list[T | None] = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_index = {
            pool.submit(copy_context().run, task): index for index, task in enumerate(tasks)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            ordered[index] = future.result()
    return ordered
