"""Shared geocoding time-budget and retry-delay helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
from agate_utils.geocoding import lookup_budget


def _delay(headers: dict[str, str] | None, attempt: int = 1) -> float:
    response = httpx.Response(429, headers=headers or {})
    return lookup_budget.retry_delay_seconds(
        response, attempt=attempt, base_delay_s=4.0, max_delay_s=30.0
    )


def test_retry_after_seconds_is_honored_and_capped() -> None:
    assert _delay({"Retry-After": "12"}) == 12.0
    assert _delay({"Retry-After": "600"}) == 30.0


def test_retry_after_http_date_is_honored() -> None:
    soon = format_datetime(datetime.now(UTC) + timedelta(seconds=20), usegmt=True)
    assert 15.0 <= _delay({"Retry-After": soon}) <= 20.0


def test_backoff_is_exponential_without_retry_after() -> None:
    assert _delay(None, attempt=1) == 4.0
    assert _delay(None, attempt=3) == 16.0
    assert _delay(None, attempt=5) == 30.0
    assert lookup_budget.retry_delay_seconds(
        None, attempt=2, base_delay_s=1.0, max_delay_s=30.0
    ) == 2.0


def test_sleep_before_deadline_refuses_a_sleep_that_would_pass_the_deadline(
    monkeypatch,
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    deadline = lookup_budget.new_deadline(10.0)

    assert lookup_budget.sleep_before_deadline(1.0, deadline) is True
    assert lookup_budget.sleep_before_deadline(60.0, deadline) is False
    assert slept == [1.0]
