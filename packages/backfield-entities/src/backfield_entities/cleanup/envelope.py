"""Request and response shapes shared by every cleanup apply route."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ItemStatus = Literal["would_apply", "applied", "noop", "error"]

# Reason codes. Callers may rely on these; new ones can be added.
REASON_RUN_NOT_OPEN = "run_not_open"
REASON_CEILING_REACHED = "ceiling_reached"
REASON_NOT_FOUND = "not_found"
REASON_SAME_CANONICAL = "same_canonical"
REASON_GUARD_REFUSED = "guard_refused"
REASON_ALREADY_MERGED = "already_merged"
REASON_NO_CHANGE = "no_change"
REASON_ALREADY_PRESENT = "already_present"
REASON_ALREADY_SUPPRESSED = "already_suppressed"
REASON_UNKNOWN_CHECK = "unknown_check"
REASON_INVALID_ITEM = "invalid_item"
REASON_ALREADY_DISMISSED = "already_dismissed"
REASON_NOT_DISMISSED = "not_dismissed"
REASON_LEDGER_FAILED = "ledger_failed"
REASON_FAILED = "failed"

MAX_ITEMS_PER_REQUEST = 100
MAX_ITEM_ID_LENGTH = 200


class ItemResult(BaseModel):
    """What happened to one item of an apply request."""

    item_id: str
    status: ItemStatus
    reason: str | None = Field(
        default=None, description="A reason code for noop and error results."
    )
    message: str | None = Field(
        default=None, description="Plain-language detail, such as what a guard refused."
    )
    action_id: str | None = Field(default=None, description="The ledger row, once applied.")
    reindex_queued: bool = False


class ApplyCounts(BaseModel):
    would_apply: int = 0
    applied: int = 0
    noop: int = 0
    error: int = 0


def count_statuses(statuses: list[ItemStatus]) -> ApplyCounts:
    counts = ApplyCounts()
    for status in statuses:
        setattr(counts, status, getattr(counts, status) + 1)
    return counts
