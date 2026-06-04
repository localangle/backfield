"""LiteLLM-backed embedding batches with normalized routing and errors."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import litellm
from backfield_db import BackfieldAiModelConfig, BackfieldProject
from sqlmodel import Session

from backfield_ai.constants import (
    AI_MODEL_KIND_EMBEDDING,
    COST_ESTIMATE_SOURCE_UNAVAILABLE,
    DEFAULT_AI_CURRENCY,
)
from backfield_ai.cost_estimate import litellm_estimated_cost_from_response
from backfield_ai.credentials import organization_llm_api_keys
from backfield_ai.litellm_model import effective_litellm_model_row
from backfield_ai.tracking_context import persist_llm_attempt

logger = logging.getLogger(__name__)


class EmbeddingConfigurationError(ValueError):
    """Missing inputs, credentials, or catalog state for an embedding call."""


class EmbeddingModelKindError(ValueError):
    """A generative catalog row was passed to the embedding path (or the reverse)."""


@dataclass(frozen=True)
class EmbeddingItemResult:
    index: int
    vector: list[float] | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class LiteLLMEmbeddingBatchResult:
    litellm_model: str
    provider: str
    provider_model_id: str
    dimensions: int | None
    items: list[EmbeddingItemResult]
    prompt_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    currency: str
    cost_estimate_incomplete: bool
    cost_estimate_source: str
    latency_ms: int
    batch_error: str | None = None
    raw_response: Any | None = None


def assert_model_config_is_embedding(cfg: BackfieldAiModelConfig) -> None:
    if str(cfg.model_kind) != AI_MODEL_KIND_EMBEDDING:
        raise EmbeddingModelKindError(
            f"Model configuration {cfg.id!r} is {cfg.model_kind!r}; embedding calls require "
            f"{AI_MODEL_KIND_EMBEDDING!r}.",
        )


def _provider_fields(litellm_model: str) -> tuple[str, str]:
    provider = ""
    provider_model_id = litellm_model
    if "/" in litellm_model:
        provider, _, rest = litellm_model.partition("/")
        provider_model_id = rest or litellm_model
    elif litellm_model.startswith("text-embedding"):
        provider = "openai"
        provider_model_id = litellm_model
    return provider or "unknown", provider_model_id


def _response_field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _coerce_embedding_vector(raw: Any) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [float(x) for x in raw]
    if isinstance(raw, tuple):
        return [float(x) for x in raw]
    if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes, dict)):
        try:
            return [float(x) for x in raw]
        except (TypeError, ValueError):
            return None
    return None


def _usage_from_embedding_response(resp: Any) -> tuple[int | None, int | None]:
    usage = _response_field(resp, "usage")
    if usage is None:
        return None, None
    pt_raw = _response_field(usage, "prompt_tokens")
    tt_raw = _response_field(usage, "total_tokens")
    pt = int(pt_raw) if pt_raw is not None else None
    tt = int(tt_raw) if tt_raw is not None else None
    return pt, tt


def _vectors_from_embedding_response(resp: Any, *, expected_count: int) -> list[list[float]]:
    data = _response_field(resp, "data")
    if not isinstance(data, list) or not data:
        raise EmbeddingConfigurationError("LiteLLM embedding response contained no vectors.")
    by_index: dict[int, list[float]] = {}
    for item in data:
        idx_raw = _response_field(item, "index", len(by_index))
        idx = int(idx_raw) if idx_raw is not None else len(by_index)
        emb = _coerce_embedding_vector(_response_field(item, "embedding"))
        if emb is None:
            raise EmbeddingConfigurationError(
                f"LiteLLM embedding item at index {idx} had no vector.",
            )
        by_index[idx] = emb
    out: list[list[float]] = []
    for i in range(expected_count):
        if i not in by_index:
            raise EmbeddingConfigurationError(
                f"LiteLLM embedding response missing index {i} (got {sorted(by_index)}).",
            )
        out.append(by_index[i])
    return out


# Short, natural phrase for catalog connection tests (not a single token).
EMBEDDING_CONNECTION_TEST_TEXT = "Connection test for organization embedding model."


def _embedding_cost_fields(
    *,
    resp: Any | None,
    litellm_model: str,
    prompt_tokens: int | None,
    total_tokens: int | None,
) -> tuple[Decimal | None, str, bool, str]:
    est_cost, cost_incomplete, cost_source, currency = litellm_estimated_cost_from_response(
        resp,
        litellm_model=litellm_model,
    )
    if prompt_tokens is None and total_tokens is None:
        cost_incomplete = True
    return est_cost, currency, cost_incomplete, cost_source


def _persist_embedding_attempt_if_tracked(
    result: LiteLLMEmbeddingBatchResult,
    *,
    model_config_id: str | None,
) -> None:
    status = "succeeded" if result.batch_error is None else "failed"
    err_type: str | None = None
    err_msg: str | None = None
    if result.batch_error:
        err_type = "EmbeddingBatchError"
        err_msg = result.batch_error[:2000]
    snap = {"provider": result.provider, "provider_model_id": result.provider_model_id}
    persist_llm_attempt(
        provider=result.provider,
        provider_model_id=result.provider_model_id,
        status=status,
        attempt_number=1,
        model_config_id=model_config_id,
        model_config_snapshot_json=snap,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=None,
        total_tokens=result.total_tokens,
        estimated_cost=result.estimated_cost,
        currency=result.currency,
        cost_estimate_incomplete=result.cost_estimate_incomplete,
        latency_ms=result.latency_ms,
        provider_request_id=None,
        error_type=err_type,
        error_message=err_msg,
        cost_estimate_source=result.cost_estimate_source,
        model_kind=AI_MODEL_KIND_EMBEDDING,
    )


def embed_texts_sync(
    *,
    litellm_model: str,
    texts: list[str],
    api_key: str | None,
    api_base: str | None = None,
    timeout: float = 120.0,
    model_config_id: str | None = None,
    track_attempt: bool = True,
) -> LiteLLMEmbeddingBatchResult:
    """Embed a batch of strings via LiteLLM (no Backfield-level retries)."""
    if not texts:
        raise EmbeddingConfigurationError("At least one text is required for embedding.")

    lm = litellm_model.strip()
    if not lm:
        raise EmbeddingConfigurationError("litellm_model is empty.")

    provider, provider_model_id = _provider_fields(lm)
    t0 = time.perf_counter()

    kwargs: dict[str, Any] = {
        "model": lm,
        "input": texts,
        "timeout": timeout,
        "num_retries": 0,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base and str(api_base).strip():
        kwargs["api_base"] = str(api_base).strip()

    try:
        resp = litellm.embedding(**kwargs)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        msg = str(exc)[:2000]
        logger.warning("LiteLLM embedding failed for model=%s: %s", lm, msg)
        result = LiteLLMEmbeddingBatchResult(
            litellm_model=lm,
            provider=provider,
            provider_model_id=provider_model_id,
            dimensions=None,
            items=[
                EmbeddingItemResult(
                    index=i,
                    vector=None,
                    error_code="provider",
                    error_message=msg,
                )
                for i in range(len(texts))
            ],
            prompt_tokens=None,
            total_tokens=None,
            estimated_cost=None,
            currency=DEFAULT_AI_CURRENCY,
            cost_estimate_incomplete=True,
            cost_estimate_source=COST_ESTIMATE_SOURCE_UNAVAILABLE,
            latency_ms=latency_ms,
            batch_error=msg,
            raw_response=None,
        )
        if track_attempt:
            _persist_embedding_attempt_if_tracked(result, model_config_id=model_config_id)
        return result

    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        vectors = _vectors_from_embedding_response(resp, expected_count=len(texts))
    except EmbeddingConfigurationError as exc:
        msg = str(exc)[:2000]
        logger.warning("LiteLLM embedding response parse failed for model=%s: %s", lm, msg)
        pt, tt = _usage_from_embedding_response(resp)
        est_cost, currency, cost_incomplete, cost_source = _embedding_cost_fields(
            resp=resp,
            litellm_model=lm,
            prompt_tokens=pt,
            total_tokens=tt,
        )
        result = LiteLLMEmbeddingBatchResult(
            litellm_model=lm,
            provider=provider,
            provider_model_id=provider_model_id,
            dimensions=None,
            items=[
                EmbeddingItemResult(
                    index=i,
                    vector=None,
                    error_code="provider",
                    error_message=msg,
                )
                for i in range(len(texts))
            ],
            prompt_tokens=pt,
            total_tokens=tt,
            estimated_cost=est_cost,
            currency=currency,
            cost_estimate_incomplete=cost_incomplete,
            cost_estimate_source=cost_source,
            latency_ms=latency_ms,
            batch_error=msg,
            raw_response=resp,
        )
        if track_attempt:
            _persist_embedding_attempt_if_tracked(result, model_config_id=model_config_id)
        return result
    pt, tt = _usage_from_embedding_response(resp)
    dims = len(vectors[0]) if vectors else None
    est_cost, currency, cost_incomplete, cost_source = _embedding_cost_fields(
        resp=resp,
        litellm_model=lm,
        prompt_tokens=pt,
        total_tokens=tt,
    )
    result = LiteLLMEmbeddingBatchResult(
        litellm_model=lm,
        provider=provider,
        provider_model_id=provider_model_id,
        dimensions=dims,
        items=[
            EmbeddingItemResult(index=i, vector=vec, error_code=None, error_message=None)
            for i, vec in enumerate(vectors)
        ],
        prompt_tokens=pt,
        total_tokens=tt,
        estimated_cost=est_cost,
        currency=currency,
        cost_estimate_incomplete=cost_incomplete,
        cost_estimate_source=cost_source,
        latency_ms=latency_ms,
        batch_error=None,
        raw_response=resp,
    )
    if track_attempt:
        _persist_embedding_attempt_if_tracked(result, model_config_id=model_config_id)
    return result


def _api_key_for_catalog_provider(
    *,
    session: Session,
    organization_id: int,
    provider: str,
) -> str | None:
    keys = organization_llm_api_keys(session, organization_id)
    prov = provider.strip().lower()
    if prov == "openai":
        return keys.get("OPENAI_API_KEY")
    if prov == "anthropic":
        return keys.get("ANTHROPIC_API_KEY")
    if prov == "gemini":
        return keys.get("GEMINI_API_KEY")
    if prov == "openrouter":
        return keys.get("OPENROUTER_API_KEY")
    if prov == "azure":
        return keys.get("AZURE_API_KEY")
    return (
        keys.get("OPENAI_API_KEY")
        or keys.get("ANTHROPIC_API_KEY")
        or keys.get("GEMINI_API_KEY")
        or keys.get("OPENROUTER_API_KEY")
        or keys.get("AZURE_API_KEY")
    )


def embed_texts_for_model_config(
    session: Session,
    *,
    project_id: int,
    model_config_id: str,
    texts: list[str],
    timeout: float = 120.0,
) -> LiteLLMEmbeddingBatchResult:
    """Resolve catalog auth for an embedding model and run a LiteLLM batch."""
    from backfield_ai.catalog_runtime import resolve_llm_auth_for_model_config
    from backfield_ai.model_resolve import _load_enabled_org_config

    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise EmbeddingConfigurationError("Project not found.")

    org_id = int(proj.organization_id)
    cfg = _load_enabled_org_config(
        session,
        organization_id=org_id,
        project_id=project_id,
        config_id=model_config_id.strip(),
    )
    assert_model_config_is_embedding(cfg)

    lm, api_key, api_base = resolve_llm_auth_for_model_config(
        session,
        project_id=project_id,
        model_config_id=model_config_id,
        fallback_litellm_model=effective_litellm_model_row(
            litellm_model=cfg.litellm_model,
            provider=str(cfg.provider),
            provider_model_id=str(cfg.provider_model_id),
        ),
    )
    if not api_key:
        api_key = _api_key_for_catalog_provider(
            session=session,
            organization_id=org_id,
            provider=str(cfg.provider),
        )
    if not api_key:
        raise EmbeddingConfigurationError(
            "No provider credentials configured for this organization.",
        )
    low_lm = lm.strip().lower()
    if low_lm.startswith("azure/") and not (api_base or "").strip():
        api_base = os.getenv("AZURE_API_BASE")
    if low_lm.startswith("azure/") and not (api_base or "").strip():
        raise EmbeddingConfigurationError(
            "Azure OpenAI embeddings require an API base URL on the credential or host env.",
        )

    return embed_texts_sync(
        litellm_model=lm,
        texts=texts,
        api_key=api_key,
        api_base=api_base,
        timeout=timeout,
        model_config_id=model_config_id.strip(),
    )
