"""Model-aware prompt size preflight using LiteLLM metadata and token counters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# When LiteLLM has no context metadata for a model, assume a large modern window
# so uncataloged OpenRouter / vendor slugs are not rejected as ~8k models.
UNKNOWN_MODEL_CONTEXT_TOKENS = 200_000
DEFAULT_OUTPUT_RESERVE_TOKENS = 1500
DEFAULT_SAFETY_MARGIN_TOKENS = 256


class PromptBudgetError(ValueError):
    """Raised when a composed prompt exceeds the available model context budget."""


@dataclass(frozen=True)
class ModelContextLimits:
    litellm_model: str
    max_input_tokens: int
    max_output_tokens: int | None
    source: str


@dataclass(frozen=True)
class PromptBudgetCheck:
    litellm_model: str
    prompt_tokens: int
    max_input_tokens: int
    reserved_output_tokens: int
    available_input_tokens: int
    fits: bool
    source: str


def resolve_model_context_limits(litellm_model: str) -> ModelContextLimits:
    """Return input/output context limits for ``litellm_model``."""
    model = (litellm_model or "").strip()
    if not model:
        return ModelContextLimits(
            litellm_model="",
            max_input_tokens=UNKNOWN_MODEL_CONTEXT_TOKENS,
            max_output_tokens=None,
            source="unknown_empty_model",
        )

    try:
        import litellm

        info = litellm.get_model_info(model)
    except Exception as exc:  # noqa: BLE001 - provider metadata is best-effort
        logger.debug("LiteLLM get_model_info failed for %s: %s", model, exc)
        info = None

    if isinstance(info, dict):
        max_input = _positive_int(info.get("max_input_tokens"))
        max_output = _positive_int(info.get("max_output_tokens"))
        max_total = _positive_int(info.get("max_tokens"))
        if max_input is None and max_total is not None:
            # Some entries store a combined window under max_tokens.
            max_input = max_total
        if max_input is not None:
            return ModelContextLimits(
                litellm_model=model,
                max_input_tokens=max_input,
                max_output_tokens=max_output,
                source="litellm_model_info",
            )

    return ModelContextLimits(
        litellm_model=model,
        max_input_tokens=UNKNOWN_MODEL_CONTEXT_TOKENS,
        max_output_tokens=None,
        source="fallback_unknown",
    )


def count_message_tokens(litellm_model: str, messages: list[dict[str, str]]) -> int:
    """Count tokens for chat messages; fall back to char approximation."""
    model = (litellm_model or "").strip() or "gpt-4o-mini"
    try:
        import litellm

        counted = litellm.token_counter(model=model, messages=messages)
        if isinstance(counted, int) and counted >= 0:
            return counted
    except Exception as exc:  # noqa: BLE001 - best-effort counter
        logger.debug("LiteLLM token_counter failed for %s: %s", model, exc)

    total_chars = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, (total_chars + 3) // 4)


def check_prompt_budget(
    *,
    litellm_model: str,
    messages: list[dict[str, str]],
    reserved_output_tokens: int = DEFAULT_OUTPUT_RESERVE_TOKENS,
    safety_margin_tokens: int = DEFAULT_SAFETY_MARGIN_TOKENS,
) -> PromptBudgetCheck:
    """Return whether ``messages`` fit within the model input budget."""
    limits = resolve_model_context_limits(litellm_model)
    prompt_tokens = count_message_tokens(limits.litellm_model or litellm_model, messages)
    reserve = max(0, int(reserved_output_tokens))
    if limits.max_output_tokens is not None:
        reserve = min(reserve, limits.max_output_tokens)
    available = max(0, limits.max_input_tokens - reserve - max(0, int(safety_margin_tokens)))
    return PromptBudgetCheck(
        litellm_model=limits.litellm_model or litellm_model,
        prompt_tokens=prompt_tokens,
        max_input_tokens=limits.max_input_tokens,
        reserved_output_tokens=reserve,
        available_input_tokens=available,
        fits=prompt_tokens <= available,
        source=limits.source,
    )


def assert_prompt_fits(
    *,
    litellm_model: str,
    system_message: str | None,
    user_prompt: str,
    reserved_output_tokens: int = DEFAULT_OUTPUT_RESERVE_TOKENS,
    chunker_guidance: bool = True,
) -> PromptBudgetCheck:
    """Raise :class:`PromptBudgetError` when the composed prompt is too large."""
    messages: list[dict[str, str]] = []
    if system_message and system_message.strip():
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_prompt})
    check = check_prompt_budget(
        litellm_model=litellm_model,
        messages=messages,
        reserved_output_tokens=reserved_output_tokens,
    )
    if check.fits:
        return check

    guidance = (
        " Add a Document Chunker after the input step so long documents are split "
        "before extraction."
        if chunker_guidance
        else ""
    )
    raise PromptBudgetError(
        f"This document is too long for the selected model "
        f"(about {check.prompt_tokens} tokens used, {check.available_input_tokens} available)."
        f"{guidance}"
    )


def _positive_int(raw: Any) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
