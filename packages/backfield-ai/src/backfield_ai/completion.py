"""LiteLLM-backed completion with normalized usage/cost hints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import litellm

from backfield_ai.constants import COST_ESTIMATE_SOURCE_LITELLM

logger = logging.getLogger(__name__)

# Upper bound when bumping an explicit ``max_tokens`` after empty JSON + finish_reason=length.
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
    cost_estimate_source: str
    latency_ms: int
    raw_response: Any


class LiteLLMCompletionRejectedError(RuntimeError):
    """LiteLLM returned HTTP-successfully but output was unusable (empty JSON, refusal, etc.).

    Includes usage and normalized provider ids so failed attempts persist tokens accurately.
    """

    def __init__(self, message: str, *, result: LiteLLMCompletionResult) -> None:
        super().__init__(message)
        self.result = result


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
    if m.startswith("gemini/"):
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
    if isinstance(usage, dict):
        pt_raw = usage.get("prompt_tokens")
        ct_raw = usage.get("completion_tokens")
        tt_raw = usage.get("total_tokens")
    else:
        pt_raw = getattr(usage, "prompt_tokens", None)
        ct_raw = getattr(usage, "completion_tokens", None)
        tt_raw = getattr(usage, "total_tokens", None)
    return (
        int(pt_raw) if pt_raw is not None else None,
        int(ct_raw) if ct_raw is not None else None,
        int(tt_raw) if tt_raw is not None else None,
    )


def _build_completion_result(
    *,
    resp: Any,
    litellm_model: str,
    text: str,
    latency_ms: int,
) -> LiteLLMCompletionResult:
    """Normalize LiteLLM ``completion`` response into our result shape (success or rejected)."""
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
        cost_estimate_source=COST_ESTIMATE_SOURCE_LITELLM,
        latency_ms=latency_ms,
        raw_response=resp,
    )


def completion_text_sync(
    *,
    litellm_model: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    max_tokens: int | None = None,
    temperature: float | None,
    timeout: float,
    force_json_response: bool,
) -> LiteLLMCompletionResult:
    """Single LiteLLM completion (no Backfield-level retries here).

    When ``max_tokens`` is None, it is omitted so the provider applies model defaults (recommended
    for OpenAI to avoid caps below the model maximum).
    """
    kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": messages,
        "timeout": timeout,
        "num_retries": 0,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
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
        latency_ms_ref = int((time.perf_counter() - t0) * 1000)
        partial = _build_completion_result(
            resp=resp,
            litellm_model=litellm_model,
            text="",
            latency_ms=latency_ms_ref,
        )
        raise LiteLLMCompletionRejectedError(
            f"Model refused to produce output: {refusal!r}",
            result=partial,
        )

    # Large prompts + JSON mode can burn the whole completion budget with no visible text yet.
    # Only bump when we sent explicit max_tokens; else the provider already used its default.
    if force_json_response and text == "" and finish == "length":
        current = kwargs.get("max_tokens")
        if current is not None:
            current_cap = int(current)
            bumped = min(max(current_cap * 2, 8192), _MAX_OUTPUT_RETRY_CEILING)
            if bumped > current_cap:
                logger.info(
                    "LiteLLM empty JSON + finish_reason=length; retry max_tokens=%s (was %s)",
                    bumped,
                    current_cap,
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
        mt_display = kwargs.get("max_tokens")
        if mt_display is None:
            mt_display = "omitted (provider default)"
        partial = _build_completion_result(
            resp=resp,
            litellm_model=litellm_model,
            text="",
            latency_ms=latency_ms,
        )
        raise LiteLLMCompletionRejectedError(
            "LiteLLM returned empty assistant content while JSON output was required "
            f"(model={litellm_model!r}, finish_reason={finish!r}, "
            f"max_tokens={mt_display}, approx_prompt_chars={prompt_chars}). "
            "If finish_reason is 'length', the completion budget was exhausted before any JSON was "
            "emitted—shorten the input or pass a higher explicit max_tokens if your provider "
            "requires one.",
            result=partial,
        )

    return _build_completion_result(
        resp=resp,
        litellm_model=litellm_model,
        text=text,
        latency_ms=latency_ms,
    )
