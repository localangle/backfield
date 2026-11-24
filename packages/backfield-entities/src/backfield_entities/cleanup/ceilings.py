"""Per-run ceilings on applied actions, from environment settings (see the ledger design note)."""

from __future__ import annotations

import os
from typing import Literal

from backfield_db import StylebookCleanupAction
from sqlalchemy import func
from sqlmodel import Session, select

OperationClass = Literal[
    "merge", "edit", "alias", "dismissal", "decision", "retirement", "deletion"
]
OPERATION_CLASSES: tuple[OperationClass, ...] = (
    "merge",
    "edit",
    "alias",
    "dismissal",
    "decision",
    "retirement",
    "deletion",
)

# Sized from the 2024 passes with headroom; retirements and deletions are hardest to reverse.
DEFAULT_CEILINGS: dict[OperationClass, int] = {
    "merge": 5000,
    "edit": 5000,
    "alias": 5000,
    "dismissal": 5000,
    "decision": 5000,
    "retirement": 500,
    "deletion": 200,
}


def ceiling_setting_name(operation: OperationClass) -> str:
    return f"BACKFIELD_CLEANUP_CEILING_{operation.upper()}"


def ceiling_for(operation: OperationClass) -> int:
    """The per-run limit for one operation class. Read on every call so a restart is enough."""
    raw = os.getenv(ceiling_setting_name(operation), "").strip()
    try:
        value = int(raw) if raw else DEFAULT_CEILINGS[operation]
    except ValueError:
        return DEFAULT_CEILINGS[operation]
    return value if value >= 0 else DEFAULT_CEILINGS[operation]


def all_ceilings() -> dict[OperationClass, int]:
    return {operation: ceiling_for(operation) for operation in OPERATION_CLASSES}


def applied_count(session: Session, *, run_id: str, operation: OperationClass) -> int:
    """Actions of this class already applied in the run (dry runs write nothing, so never count)."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(StylebookCleanupAction)
            .where(
                StylebookCleanupAction.run_id == run_id,
                StylebookCleanupAction.operation == operation,
            )
        )
        or 0
    )
