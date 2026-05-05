"""LiteLLM-backed completion with normalized usage/cost hints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import litellm

logger = logging.getLogger(__name__)

# Upper bound for automatic bump when JSON mode hits max_tokens before emitting assistant text.
# Must stay above ``agate_utils.llm.DEFAULT_MAX_COMPLETION_TOKENS`` so retries can raise the budget.
_MAX_OUTPUT_RETRY_CEILING = 1_048_576


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


def _litellm_json_object_response_format_supported(litellm_model: str) -> bool:
    """Whether to pass OpenAI-style ``response_format: json_object`` through LiteLLM.

    Bare OpenAI ids (``gpt-…``) are common; org catalogs may use ``openai/…`` or ``anthropic/…``.
    Requesting JSON mode only where LiteLLM maps it reduces empty/non-JSON completions.
    """
    m = litellm_model.strip().lower()
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return True
    if m.startswith("openai/") or m.startswith("azure/"):
        return True
    if m.startswith("anthropic/"):
        return True
    return False


def _extract_message_content_text(message: Any) -> str:
    """Normalize assistant ``message.content`` from LiteLLM (string or content-block list)."""
    if message is None:
        return ""
    raw = getattr(message, "content", None)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "reasoning":
                    continue
                tx = block.get("text")
                if isinstance(tx, str) and tx.strip():
                    if btype in ("text", "output_text", None):
                        parts.append(tx)
                elif isinstance(block.get("output_text"), str):
                    parts.append(block["output_text"])
                elif isinstance(block.get("output_text"), dict):
                    inner = block["output_text"].get("text")
                    if isinstance(inner, str) and inner.strip():
                        parts.append(inner)
            else:
                tx = getattr(block, "text", None)
                if isinstance(tx, str):
                    parts.append(tx)
        return "".join(parts).strip()
    return str(raw).strip()


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
    if force_json_response and _litellm_json_object_response_format_supported(litellm_model):
        kwargs["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    resp = litellm.completion(**kwargs)

    choice = resp.choices[0]
    msg = choice.message
    text = _extract_message_content_text(msg)
    finish = getattr(choice, "finish_reason", None)

    refusal = getattr(msg, "refusal", None)
    if refusal is not None and str(refusal).strip():
        raise RuntimeError(f"Model refused to produce output: {refusal!r}")

    # Large prompts + JSON mode can burn the whole completion budget with no visible text yet.
    if force_json_response and text == "" and finish == "length":
        current_cap = int(kwargs["max_tokens"])
        bumped = min(max(current_cap * 2, 8192), _MAX_OUTPUT_RETRY_CEILING)
        if bumped > current_cap:
            logger.info(
                "LiteLLM empty JSON + finish_reason=length; retry max_tokens=%s (was %s)",
                bumped,
                kwargs["max_tokens"],
            )
            kwargs["max_tokens"] = bumped
            resp = litellm.completion(**kwargs)
            choice = resp.choices[0]
            msg = choice.message
            text = _extract_message_content_text(msg)
            finish = getattr(choice, "finish_reason", None)

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if force_json_response and text == "":
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        raise RuntimeError(
            "LiteLLM returned empty assistant content while JSON output was required "
            f"(model={litellm_model!r}, finish_reason={finish!r}, "
            f"max_tokens={kwargs['max_tokens']}, approx_prompt_chars={prompt_chars}). "
            "If finish_reason is 'length', the completion token limit was hit before any JSON was "
            "emitted—increase max_tokens or shorten the input."
        )
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
