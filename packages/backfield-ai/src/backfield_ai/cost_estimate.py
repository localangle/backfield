"""LiteLLM-based estimated cost from provider responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import litellm

from backfield_ai.constants import (
    COST_ESTIMATE_SOURCE_LITELLM,
    COST_ESTIMATE_SOURCE_NO_RESPONSE,
    COST_ESTIMATE_SOURCE_UNAVAILABLE,
    DEFAULT_AI_CURRENCY,
)


def zero_cost_for_attempt_without_response() -> tuple[Decimal, bool, str, str]:
    """Cost tuple for an attempt that failed before any response (nothing to price)."""
    return Decimal(0), False, COST_ESTIMATE_SOURCE_NO_RESPONSE, DEFAULT_AI_CURRENCY


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


def litellm_estimated_cost_from_tokens(
    litellm_model: str,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> tuple[Decimal | None, bool, str, str]:
    """Price reported token counts with LiteLLM's rates when no completion response exists.

    Decision models (Jev) answer through their own HTTP API, so there is no LiteLLM response to
    price; the counts come from the API's usage block. Returns the same tuple as
    :func:`litellm_estimated_cost_from_response`; the cost stays incomplete when the counts are
    missing or LiteLLM has no rate for the model.
    """
    if prompt_tokens is None and completion_tokens is None:
        return None, True, COST_ESTIMATE_SOURCE_UNAVAILABLE, DEFAULT_AI_CURRENCY
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=litellm_model,
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
        )
    except Exception:
        return None, True, COST_ESTIMATE_SOURCE_UNAVAILABLE, DEFAULT_AI_CURRENCY
    total_cost = Decimal(str(prompt_cost)) + Decimal(str(completion_cost))
    return total_cost, False, COST_ESTIMATE_SOURCE_LITELLM, DEFAULT_AI_CURRENCY


def decision_attempt_cost(
    litellm_model: str,
    *,
    status: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> tuple[Decimal | None, bool, str, str]:
    """Cost tuple for one decision-model attempt.

    A failed attempt that reported no usage never produced a response, so it costs nothing.
    Anything else is priced from its token counts and stays incomplete when that is impossible.
    """
    if status != "succeeded" and prompt_tokens is None and completion_tokens is None:
        return zero_cost_for_attempt_without_response()
    return litellm_estimated_cost_from_tokens(
        litellm_model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
