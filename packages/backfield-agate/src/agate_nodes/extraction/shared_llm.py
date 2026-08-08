"""Shared LLM timing, model resolution, and prompt-budget helpers for extract nodes."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from backfield_ai.prompt_budget import assert_prompt_fits

logger = logging.getLogger(__name__)

TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
CELERY_TIMEOUT_BUFFER = 300


def node_deadline_monotonic(start_time: float) -> float:
    return start_time + max(60.0, TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER)


def effective_llm_timeout(*, start_time: float, llm_timeout: int) -> float:
    max_safe_runtime = TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER
    elapsed = time.time() - start_time
    if elapsed > max_safe_runtime:
        raise TimeoutError(
            f"Node exceeded safe runtime limit ({max_safe_runtime}s) before LLM call"
        )
    remaining = max_safe_runtime - elapsed
    timeout = min(float(llm_timeout), remaining)
    if timeout < 60:
        raise TimeoutError(
            f"Insufficient time remaining ({timeout:.1f}s) for LLM call"
        )
    return timeout


def resolve_extract_litellm_model(params: Any, *, log_label: str) -> str:
    model = str(getattr(params, "model", "") or "gpt-4o-mini")
    raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
    if not raw_pid:
        return model
    try:
        from backfield_ai.model_resolve import resolve_place_extract_litellm_model
        from backfield_db.session import get_engine
        from sqlmodel import Session

        with Session(get_engine()) as res_sess:
            return resolve_place_extract_litellm_model(
                res_sess,
                int(raw_pid),
                params,
            )
    except Exception as exc:  # noqa: BLE001 - catalog optional in unit tests
        logger.warning(
            "[%s] could not resolve catalog AI model; using legacy id: %s",
            log_label,
            exc,
        )
        return model


def model_config_id_from_params(params: Any) -> str | None:
    raw_mc = getattr(params, "aiModelConfigId", None)
    if raw_mc is None:
        return None
    value = str(raw_mc).strip()
    return value or None


def preflight_unchunked_prompt(
    *,
    litellm_model: str,
    system_message: str,
    user_prompt: str,
    project_system_prompt: str | None,
) -> None:
    merged_system = system_message
    overlay = (project_system_prompt or "").strip()
    if overlay:
        merged_system = f"{system_message}\n\n{overlay}"
    assert_prompt_fits(
        litellm_model=litellm_model,
        system_message=merged_system,
        user_prompt=user_prompt,
        chunker_guidance=True,
    )
