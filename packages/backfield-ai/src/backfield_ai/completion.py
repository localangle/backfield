"""LiteLLM-backed completion with normalized usage/cost hints."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import litellm


@dataclass(frozen=True)
class LiteLLMCompletionResult:
    text: str
    provider: str
    provider_model_id: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    currency: str
    cost_estimate_incomplete: bool
    latency_ms: int
    raw_response: Any


def _usage_from_response(resp: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None, None, None
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    tt = getattr(usage, "total_tokens", None)
    return (
        int(pt) if pt is not None else None,
        int(ct) if ct is not None else None,
        int(tt) if tt is not None else None,
    )


def completion_text_sync(
    *,
    litellm_model: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    max_tokens: int,
    temperature: float | None,
    timeout: float,
    force_json_response: bool,
) -> LiteLLMCompletionResult:
    """Single LiteLLM completion (no Backfield-level retries here)."""
    kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "num_retries": 0,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if temperature is not None:
        kwargs["temperature"] = temperature
    if force_json_response and litellm_model.startswith("gpt"):
        kwargs["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    resp = litellm.completion(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    choice = resp.choices[0]
    msg = choice.message
    text = (msg.content or "").strip()
    pt, ct, tt = _usage_from_response(resp)

    incomplete = pt is None and ct is None and tt is None
    est_cost: Decimal | None = None
    currency = "USD"
    try:
        cost_val = litellm.completion_cost(completion_response=resp)
        if cost_val is not None:
            est_cost = Decimal(str(cost_val))
            incomplete = False
    except Exception:
        incomplete = True

    provider = ""
    provider_model_id = litellm_model
    if "/" in litellm_model:
        provider, _, rest = litellm_model.partition("/")
        provider_model_id = rest or litellm_model
    elif litellm_model.startswith("gpt"):
        provider = "openai"
        provider_model_id = litellm_model

    return LiteLLMCompletionResult(
        text=text,
        provider=provider or "unknown",
        provider_model_id=provider_model_id,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=tt,
        estimated_cost=est_cost,
        currency=currency,
        cost_estimate_incomplete=incomplete,
        latency_ms=latency_ms,
        raw_response=resp,
    )
