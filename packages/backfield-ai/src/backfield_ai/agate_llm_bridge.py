"""Tracked LiteLLM completion path for Agate worker runs (invoked from ``agate_utils.llm``)."""

from __future__ import annotations

import time

from backfield_ai.completion import completion_text_sync
from backfield_ai.json_clean import clean_json_response_text
from backfield_ai.tracking_context import persist_llm_attempt


def _legacy_to_litellm_model(model: str) -> str:
    m = model.strip()
    if m.startswith("claude"):
        return f"anthropic/{m}"
    return m


def _pick_api_key(
    litellm_model: str,
    openai_key: str | None,
    anthropic_key: str | None,
) -> str | None:
    if litellm_model.startswith("anthropic/") or litellm_model.startswith("claude"):
        return anthropic_key
    return openai_key


def call_llm_tracked_sync(
    prompt: str,
    model: str | None,
    system_message: str | None,
    force_json: bool,
    max_retries: int,
    temperature: float,
    max_tokens: int,
    openai_api_key: str | None,
    anthropic_api_key: str | None,
    project_system_prompt: str | None,
    timeout: float,
    model_config_id: str | None = None,
) -> str:
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    import os

    mc_norm = (model_config_id or "").strip() or None

    raw_model = model or os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    lm_model = _legacy_to_litellm_model(raw_model.strip())

    if project_system_prompt:
        system_message = project_system_prompt
    elif system_message is None:
        if force_json:
            system_message = "You are a helpful assistant that returns only structured JSON output."
        else:
            system_message = (
                "You are a helpful assistant that returns direct, concise responses "
                "without markdown formatting or explanations."
            )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt},
    ]

    api_key = _pick_api_key(lm_model, openai_api_key, anthropic_api_key)
    if not api_key:
        raise ValueError("No API key available for the selected model.")

    is_gpt5 = lm_model.startswith("gpt-5")
    temp_arg: float | None = None if is_gpt5 else float(temperature)

    last_err: Exception | None = None
    for attempt_idx in range(max_retries):
        try:
            result = completion_text_sync(
                litellm_model=lm_model,
                messages=messages,
                api_key=api_key,
                max_tokens=max_tokens,
                temperature=temp_arg,
                timeout=float(timeout),
                force_json_response=bool(force_json),
            )
            snap = {"provider": result.provider, "provider_model_id": result.provider_model_id}
            persist_llm_attempt(
                provider=result.provider,
                provider_model_id=result.provider_model_id,
                status="succeeded",
                attempt_number=attempt_idx + 1,
                model_config_id=mc_norm,
                model_config_snapshot_json=snap,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                estimated_cost=result.estimated_cost,
                currency=result.currency,
                cost_estimate_incomplete=result.cost_estimate_incomplete,
                latency_ms=result.latency_ms,
                provider_request_id=None,
                error_type=None,
                error_message=None,
            )
            text = result.text
            return clean_json_response_text(text) if force_json else text
        except Exception as exc:
            last_err = exc
            err_type = type(exc).__name__
            err_msg = str(exc)[:2000]
            snap = {"litellm_model": lm_model}
            persist_llm_attempt(
                provider="unknown",
                provider_model_id=lm_model,
                status="failed",
                attempt_number=attempt_idx + 1,
                model_config_id=mc_norm,
                model_config_snapshot_json=snap,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                estimated_cost=None,
                currency="USD",
                cost_estimate_incomplete=True,
                latency_ms=None,
                provider_request_id=None,
                error_type=err_type,
                error_message=err_msg,
            )
            if attempt_idx < max_retries - 1:
                wait_time = 2**attempt_idx
                time.sleep(wait_time)
            else:
                raise Exception(f"LLM call failed after {max_retries} attempts: {exc}") from exc

    raise Exception(f"LLM call failed after {max_retries} attempts: {last_err}")
