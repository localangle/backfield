"""Record usage for decision-model (Jev) calls, which answer through their own HTTP API."""

from __future__ import annotations

import logging
from typing import Any

from backfield_ai.constants import AI_MODEL_KIND_DECISION
from backfield_ai.cost_estimate import decision_attempt_cost
from backfield_ai.tracking_context import persist_llm_attempt

logger = logging.getLogger(__name__)

_DECISION_PROVIDER = "typesafe"


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def record_decision_attempt(
    payload: dict[str, Any],
    *,
    requested_model: str,
    model_config_id: str | None,
    latency_ms: int,
    status: str,
    error_type: str | None,
    error_message: str | None,
) -> None:
    """Persist one decision-model attempt with a cost priced from its reported token usage.

    ``payload`` is the API response body (empty when the call failed before a response).
    Recording problems are logged and never fail the node.
    """
    reported = payload.get("model")
    if isinstance(reported, str) and reported.strip():
        provider_model_id = reported.strip()
    else:
        provider_model_id = requested_model
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt_tokens = _as_int(usage.get("input_tokens"))
    completion_tokens = _as_int(usage.get("output_tokens"))
    total_tokens = None
    if prompt_tokens is not None or completion_tokens is not None:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    estimated_cost, cost_incomplete, cost_source, currency = decision_attempt_cost(
        f"{_DECISION_PROVIDER}/{provider_model_id}",
        status=status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    try:
        persist_llm_attempt(
            provider=_DECISION_PROVIDER,
            provider_model_id=provider_model_id,
            status=status,
            attempt_number=1,
            model_config_id=model_config_id,
            model_config_snapshot_json={
                "provider": _DECISION_PROVIDER,
                "provider_model_id": provider_model_id,
            },
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            currency=currency,
            cost_estimate_incomplete=cost_incomplete,
            latency_ms=latency_ms,
            provider_request_id=None,
            error_type=error_type,
            error_message=error_message,
            cost_estimate_source=cost_source,
            model_kind=AI_MODEL_KIND_DECISION,
        )
    except Exception:
        logger.warning("Could not record decision model usage", exc_info=True)
