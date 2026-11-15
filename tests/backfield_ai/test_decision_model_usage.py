"""Jev decision-model calls record priced usage in the AI call table."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from agate_nodes.organization_enrich import remote as organization_remote
from agate_nodes.person_enrich import remote as person_remote
from backfield_ai.constants import COST_ESTIMATE_SOURCE_LITELLM, COST_ESTIMATE_SOURCE_UNAVAILABLE


@pytest.mark.parametrize("remote", [person_remote, organization_remote])
def test_decision_attempt_with_usage_is_priced(
    remote: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(remote, "persist_llm_attempt", lambda **kwargs: recorded.append(kwargs))

    remote._record_decision_attempt(
        {"model": "jev-1.13.0", "usage": {"input_tokens": 2_000, "output_tokens": 30}},
        requested_model="jev-1.13.0",
        model_config_id=None,
        latency_ms=120,
        status="succeeded",
        error_type=None,
        error_message=None,
    )

    [row] = recorded
    assert row["cost_estimate_incomplete"] is False
    assert row["cost_estimate_source"] == COST_ESTIMATE_SOURCE_LITELLM
    assert row["estimated_cost"] > Decimal(0)
    assert row["prompt_tokens"] == 2_000


@pytest.mark.parametrize("remote", [person_remote, organization_remote])
def test_decision_attempt_without_usage_stays_incomplete(
    remote: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(remote, "persist_llm_attempt", lambda **kwargs: recorded.append(kwargs))

    remote._record_decision_attempt(
        {},
        requested_model="jev-1.13.0",
        model_config_id=None,
        latency_ms=120,
        status="failed",
        error_type="Timeout",
        error_message="timed out",
    )

    [row] = recorded
    assert row["cost_estimate_incomplete"] is True
    assert row["estimated_cost"] is None
    assert row["cost_estimate_source"] == COST_ESTIMATE_SOURCE_UNAVAILABLE
