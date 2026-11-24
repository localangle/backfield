"""The per-item loop every cleanup apply route shares.

Each item commits (or rolls back) on its own, so one failing item never undoes the others. An
operation supplies a function that does one item and returns its result; this module turns raised
errors into per-item error results and decides between commit and rollback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

from backfield_db import StylebookCleanupRun
from sqlmodel import Session

from backfield_entities.cleanup.ceilings import OperationClass, applied_count, ceiling_for
from backfield_entities.cleanup.envelope import (
    REASON_CEILING_REACHED,
    REASON_FAILED,
    REASON_GUARD_REFUSED,
    REASON_LEDGER_FAILED,
    REASON_NOT_FOUND,
    REASON_RUN_NOT_OPEN,
    ItemResult,
)
from backfield_entities.cleanup.runs import require_run

logger = logging.getLogger(__name__)

_NOT_FOUND_MARKER = "not in this stylebook"


class HasItemId(Protocol):
    item_id: str


ItemT = TypeVar("ItemT", bound=HasItemId)
ResultT = TypeVar("ResultT", bound=ItemResult)


class ItemRefused(Exception):
    """An item that cannot be applied, with the reason code and plain-language message to report."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class LedgerError(Exception):
    """The ledger row could not be written, so the change must not stand."""


def run_not_open_refusal(session: Session, *, stylebook_id: int, run_id: str) -> ItemRefused | None:
    """Refusal for an item whose run has been closed or aborted; None while it is open.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook.
    """
    run: StylebookCleanupRun = require_run(session, stylebook_id=stylebook_id, run_id=run_id)
    if run.status != "open":
        return ItemRefused(REASON_RUN_NOT_OPEN, f"The run is {run.status}.")
    return None


def ceiling_refusal(
    session: Session, *, run_id: str, operation: OperationClass, noun: str
) -> ItemRefused | None:
    """Refusal once the run has applied as many of this operation as the instance allows."""
    if applied_count(session, run_id=run_id, operation=operation) >= ceiling_for(operation):
        return ItemRefused(
            REASON_CEILING_REACHED,
            f"This run has reached the limit for {noun}. Open a new run to continue.",
        )
    return None


def process_items(
    session: Session,
    *,
    items: Sequence[ItemT],
    operation_noun: str,
    apply_one: Callable[[ItemT], ResultT],
    error_result: Callable[[ItemT, str, str], ResultT],
) -> list[ResultT]:
    """Run ``apply_one`` for each item in order and report every outcome.

    An ``applied`` result is committed; every other result (a dry run, a noop, an error) rolls the
    item's work back. ``apply_one`` may raise ``ItemRefused`` or ``LedgerError``; a ``ValueError``
    from the library is reported as a guard refusal (or not found).
    """
    results: list[ResultT] = []
    for item in items:
        try:
            result = apply_one(item)
            if result.status == "applied":
                session.commit()
            else:
                session.rollback()
        except ItemRefused as refusal:
            session.rollback()
            result = error_result(item, refusal.reason, refusal.message)
        except ValueError as exc:
            session.rollback()
            message = str(exc)
            reason = REASON_NOT_FOUND if _NOT_FOUND_MARKER in message else REASON_GUARD_REFUSED
            result = error_result(item, reason, message)
        except LedgerError:
            session.rollback()
            logger.exception("Cleanup ledger write failed for item %s", item.item_id)
            result = error_result(item, REASON_LEDGER_FAILED, "The change was not saved.")
        except Exception:
            session.rollback()
            logger.exception("Cleanup %s failed for item %s", operation_noun, item.item_id)
            result = error_result(
                item, REASON_FAILED, f"The {operation_noun} could not be completed."
            )
        results.append(result)
    return results
