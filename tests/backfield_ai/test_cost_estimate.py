"""LiteLLM cost estimation helper."""

from __future__ import annotations

from decimal import Decimal

import litellm
import pytest
from backfield_ai.constants import COST_ESTIMATE_SOURCE_LITELLM, COST_ESTIMATE_SOURCE_UNAVAILABLE
from backfield_ai.cost_estimate import (
    litellm_estimated_cost_from_response,
    litellm_estimated_cost_from_tokens,
)


def test_litellm_estimated_cost_none_response() -> None:
    est, incomplete, source, currency = litellm_estimated_cost_from_response(None)
    assert est is None
    assert incomplete is True
    assert source == COST_ESTIMATE_SOURCE_UNAVAILABLE
    assert currency == "USD"


def test_litellm_estimated_cost_from_embedding_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = {
        "data": [{"index": 0, "embedding": [0.1]}],
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 2e-7)
    est, incomplete, source, _currency = litellm_estimated_cost_from_response(
        resp,
        litellm_model="openai/text-embedding-3-small",
    )
    assert est == Decimal("2E-7")
    assert incomplete is False
    assert source == COST_ESTIMATE_SOURCE_LITELLM


def test_cost_from_tokens_uses_litellm_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(litellm, "cost_per_token", lambda **_kw: (4.2e-05, 0.0))
    est, incomplete, source, currency = litellm_estimated_cost_from_tokens(
        "typesafe/jev-1.13.0", prompt_tokens=1000, completion_tokens=20
    )
    assert est == Decimal("4.2E-5")
    assert incomplete is False
    assert source == COST_ESTIMATE_SOURCE_LITELLM
    assert currency == "USD"


def test_cost_from_tokens_prices_the_real_jev_catalog_entry() -> None:
    est, incomplete, _source, _currency = litellm_estimated_cost_from_tokens(
        "typesafe/jev-1.13.0", prompt_tokens=1_000_000, completion_tokens=5_000
    )
    assert incomplete is False
    assert est is not None and est > 0


def test_cost_from_tokens_stays_incomplete_without_counts() -> None:
    est, incomplete, source, _currency = litellm_estimated_cost_from_tokens(
        "typesafe/jev-1.13.0", prompt_tokens=None, completion_tokens=None
    )
    assert est is None
    assert incomplete is True
    assert source == COST_ESTIMATE_SOURCE_UNAVAILABLE


def test_cost_from_tokens_stays_incomplete_for_unpriced_model() -> None:
    est, incomplete, source, _currency = litellm_estimated_cost_from_tokens(
        "typesafe/not-a-real-model", prompt_tokens=10, completion_tokens=2
    )
    assert est is None
    assert incomplete is True
    assert source == COST_ESTIMATE_SOURCE_UNAVAILABLE
