"""Worker/run-scoped LLM attempt persistence (no prompt or response body)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backfield_db import BackfieldAiCallRecord
from sqlmodel import Session

from backfield_ai.constants import COST_ESTIMATE_SOURCE_UNAVAILABLE


@dataclass(frozen=True)
class LlmAttemptTrackingContext:
    session: Session
    project_id: int
    run_id: str
    # Per-file S3/batch runs set this to ``agate_processed_item.id``; single-graph runs leave None.
    processed_item_id: int | None = None


_CTX: ContextVar[LlmAttemptTrackingContext | None] = ContextVar("bf_llm_track_ctx", default=None)

_CURRENT_NODE_ID: ContextVar[str | None] = ContextVar("bf_llm_current_node_id", default=None)
_CURRENT_NODE_TYPE: ContextVar[str | None] = ContextVar("bf_llm_current_node_type", default=None)


def current_llm_tracking_context() -> LlmAttemptTrackingContext | None:
    return _CTX.get()


def attach_llm_tracking_context(ctx: LlmAttemptTrackingContext):
    return _CTX.set(ctx)


def reset_llm_tracking_context(token: object) -> None:
    _CTX.reset(token)


def set_llm_tracking_current_node(node_id: str | None, node_type: str | None) -> None:
    """Best-effort scope for the graph node executing during worker runs (React Flow id + type)."""
    _CURRENT_NODE_ID.set(node_id)
    _CURRENT_NODE_TYPE.set(node_type)


def persist_llm_attempt(
    *,
    provider: str,
    provider_model_id: str,
    status: str,
    attempt_number: int,
    model_config_id: str | None,
    model_config_snapshot_json: dict[str, Any] | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    estimated_cost: Decimal | None,
    currency: str,
    cost_estimate_incomplete: bool,
    latency_ms: int | None,
    provider_request_id: str | None,
    error_type: str | None,
    error_message: str | None,
    cost_estimate_source: str | None = None,
) -> None:
    ctx = current_llm_tracking_context()
    if ctx is None:
        return
    row = BackfieldAiCallRecord(
        project_id=ctx.project_id,
        run_id=ctx.run_id,
        processed_item_id=ctx.processed_item_id,
        node_id=_CURRENT_NODE_ID.get(),
        node_type=_CURRENT_NODE_TYPE.get(),
        model_config_id=model_config_id,
        model_config_snapshot_json=model_config_snapshot_json,
        provider=provider,
        provider_model_id=provider_model_id,
        model_kind="generative",
        status=status,
        attempt_number=attempt_number,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        currency=currency,
        cost_estimate_source=cost_estimate_source or COST_ESTIMATE_SOURCE_UNAVAILABLE,
        cost_estimate_incomplete=cost_estimate_incomplete,
        latency_ms=latency_ms,
        provider_request_id=provider_request_id,
        error_type=error_type,
        error_message=error_message,
    )
    ctx.session.add(row)
    ctx.session.flush()
