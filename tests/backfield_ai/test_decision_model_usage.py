"""Jev decision-model calls record priced usage in the AI call table."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import litellm
import pytest
from backfield_ai import decision_usage
from backfield_ai.constants import (
    COST_ESTIMATE_SOURCE_LITELLM,
    COST_ESTIMATE_SOURCE_NO_RESPONSE,
    COST_ESTIMATE_SOURCE_UNAVAILABLE,
)


def _record(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(decision_usage, "persist_llm_attempt", lambda **kw: recorded.append(kw))
    decision_usage.record_decision_attempt(
        payload,
        requested_model="jev-1.13.0",
        model_config_id=None,
        latency_ms=120,
        status=status,
        error_type=None if status == "succeeded" else "Timeout",
        error_message=None if status == "succeeded" else "timed out",
    )
    [row] = recorded
    return row


def test_decision_attempt_with_usage_is_priced(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fixed rates keep this test independent of LiteLLM's live model catalog.
    monkeypatch.setattr(litellm, "cost_per_token", lambda **_kw: (0.002, 0.0003))

    row = _record(
        monkeypatch,
        {"model": "jev-1.13.0", "usage": {"input_tokens": 2_000, "output_tokens": 30}},
        status="succeeded",
    )

    assert row["cost_estimate_incomplete"] is False
    assert row["cost_estimate_source"] == COST_ESTIMATE_SOURCE_LITELLM
    assert row["estimated_cost"] == Decimal("0.0023")
    assert row["prompt_tokens"] == 2_000
    assert row["total_tokens"] == 2_030


def test_failed_decision_attempt_without_response_costs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _record(monkeypatch, {}, status="failed")

    assert row["cost_estimate_incomplete"] is False
    assert row["estimated_cost"] == Decimal(0)
    assert row["cost_estimate_source"] == COST_ESTIMATE_SOURCE_NO_RESPONSE


def test_successful_decision_attempt_without_usage_stays_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _record(monkeypatch, {}, status="succeeded")

    assert row["cost_estimate_incomplete"] is True
    assert row["estimated_cost"] is None
    assert row["cost_estimate_source"] == COST_ESTIMATE_SOURCE_UNAVAILABLE
