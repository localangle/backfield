"""Time-budget and retry-delay helpers shared by the geocoding providers."""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Protocol


class _HasHeaders(Protocol):
    """An ``httpx`` or ``requests`` response, which is all the retry delay needs."""

    headers: Mapping[str, str]


def new_deadline(budget_s: float) -> float:
    """Monotonic deadline ``budget_s`` seconds from now."""
    return time.monotonic() + budget_s


def remaining_s(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def sleep_before_deadline(delay_s: float, deadline: float) -> bool:
    """Sleep ``delay_s`` if it fits before ``deadline``; False means the budget would run out."""
    if delay_s >= remaining_s(deadline):
        return False
    time.sleep(delay_s)
    return True


def retry_delay_seconds(
    response: _HasHeaders | None,
    *,
    attempt: int,
    base_delay_s: float,
    max_delay_s: float,
) -> float:
    """Backoff before a retry: the server's ``Retry-After`` when sent, else exponential."""
    retry_after = _retry_after_seconds(response)
    if retry_after is not None:
        return min(retry_after, max_delay_s)
    return min(base_delay_s * 2 ** max(0, attempt - 1), max_delay_s)


def _retry_after_seconds(response: _HasHeaders | None) -> float | None:
    if response is None:
        return None
    raw = response.headers.get("Retry-After", "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        retry_at = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delta = retry_at.timestamp() - time.time()
    return delta if delta > 0 else None
