"""Parallel execution helpers for session-free LLM calls during DBOutput persist."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar, Token, copy_context
from typing import TypeVar

from sqlmodel import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Set by the DBOutput persist gate. Returns a context manager that hands the persist slot back
# while the body runs and takes a slot again afterwards.
PersistSlotPause = Callable[[], AbstractContextManager[None]]
_persist_slot_pause: ContextVar[PersistSlotPause | None] = ContextVar(
    "persist_slot_pause", default=None
)


@contextmanager
def install_persist_slot_pause(pause: PersistSlotPause) -> Iterator[None]:
    """Let session-free LLM batches in this context free the caller's persist slot."""
    token: Token[PersistSlotPause | None] = _persist_slot_pause.set(pause)
    try:
        yield
    finally:
        _persist_slot_pause.reset(token)


@contextmanager
def persist_slot_paused_for_llm() -> Iterator[None]:
    """Free the persist slot (if one is held) for the duration of the body."""
    pause = _persist_slot_pause.get()
    if pause is None:
        yield
        return
    with pause():
        yield


def canonical_adjudication_max_concurrent() -> int:
    raw = os.getenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", "12")
    try:
        return max(1, int(raw))
    except ValueError:
        return 12


def candidate_ai_review_max_concurrent() -> int:
    """Parallel LLM workers for bulk candidate queue review.

    Default caps below ``CANONICAL_ADJUDICATION_MAX_CONCURRENT`` so brief post-LLM
    writes and progress updates stay within the worker's small SQLAlchemy pool.
    """
    raw = os.getenv("CANDIDATE_AI_REVIEW_MAX_CONCURRENT")
    if raw is not None and raw.strip() != "":
        try:
            return max(1, int(raw.strip()))
        except ValueError:
            pass
    return min(canonical_adjudication_max_concurrent(), 3)


def commit_session_before_session_free_llm(session: Session) -> None:
    """Release row locks before parallel LLM work that can take tens of seconds."""
    session.commit()
    logger.debug("Committed DBOutput persist transaction before session-free LLM batch")


def run_callables_parallel(
    tasks: Sequence[Callable[[], T]],
    *,
    max_workers: int,
) -> list[T]:
    """Run callables in order; use a thread pool when max_workers > 1 and len(tasks) > 1.

    These are the session-free LLM batches of DBOutput persist, so the persist slot is handed
    back while they run: model latency is not database load and should not hold a slot.
    """
    if not tasks:
        return []
    with persist_slot_paused_for_llm():
        return _run_callables(tasks, max_workers=max_workers)


def _run_callables(tasks: Sequence[Callable[[], T]], *, max_workers: int) -> list[T]:
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
