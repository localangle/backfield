"""LiteLLM cost estimation helper."""

from __future__ import annotations

from decimal import Decimal

import litellm
import pytest
from backfield_ai.constants import COST_ESTIMATE_SOURCE_LITELLM, COST_ESTIMATE_SOURCE_UNAVAILABLE
from backfield_ai.cost_estimate import litellm_estimated_cost_from_response


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
