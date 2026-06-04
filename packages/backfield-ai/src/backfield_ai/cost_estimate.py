"""LiteLLM-based estimated cost from provider responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import litellm

from backfield_ai.constants import (
    COST_ESTIMATE_SOURCE_LITELLM,
    COST_ESTIMATE_SOURCE_UNAVAILABLE,
    DEFAULT_AI_CURRENCY,
)


def litellm_estimated_cost_from_response(
    resp: Any | None,
    *,
    litellm_model: str | None = None,
) -> tuple[Decimal | None, bool, str, str]:
    """Return ``(estimated_cost, cost_estimate_incomplete, cost_estimate_source, currency)``."""
    if resp is None:
        return None, True, COST_ESTIMATE_SOURCE_UNAVAILABLE, DEFAULT_AI_CURRENCY
    try:
        kwargs: dict[str, Any] = {"completion_response": resp}
        if litellm_model:
            kwargs["model"] = litellm_model
        cost_val = litellm.completion_cost(**kwargs)
        if cost_val is not None:
            return Decimal(str(cost_val)), False, COST_ESTIMATE_SOURCE_LITELLM, DEFAULT_AI_CURRENCY
    except Exception:
        pass
    return None, True, COST_ESTIMATE_SOURCE_LITELLM, DEFAULT_AI_CURRENCY
