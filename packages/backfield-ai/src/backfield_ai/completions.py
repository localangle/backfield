"""Catalog-backed LiteLLM text completions."""

from __future__ import annotations

import os

from backfield_db import BackfieldAiModelConfig, BackfieldProject
from sqlmodel import Session

from backfield_ai.completion import LiteLLMCompletionResult, completion_text_sync
from backfield_ai.constants import AI_MODEL_KIND_GENERATIVE
from backfield_ai.credentials import organization_llm_api_keys
from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.litellm_model import effective_litellm_model_row
from backfield_ai.model_resolve import _load_enabled_org_config


def assert_model_config_is_generative(cfg: BackfieldAiModelConfig) -> None:
    if str(cfg.model_kind) != AI_MODEL_KIND_GENERATIVE:
        raise EmbeddingConfigurationError(
            f"Model configuration {cfg.id!r} is {cfg.model_kind!r}; completion calls require "
            f"{AI_MODEL_KIND_GENERATIVE!r}.",
        )


def _api_key_for_catalog_provider(
    session: Session,
    *,
    organization_id: int,
    provider: str,
) -> str | None:
    keys = organization_llm_api_keys(session, organization_id=organization_id)
    provider_key = str(provider).strip().lower()
    if provider_key == "openai":
        return keys.get("OPENAI_API_KEY")
    if provider_key == "anthropic":
        return keys.get("ANTHROPIC_API_KEY")
    if provider_key == "gemini":
        return keys.get("GEMINI_API_KEY")
    if provider_key == "openrouter":
        return keys.get("OPENROUTER_API_KEY")
    if provider_key == "azure":
        return keys.get("AZURE_API_KEY")
    return (
        keys.get("OPENAI_API_KEY")
        or keys.get("ANTHROPIC_API_KEY")
        or keys.get("GEMINI_API_KEY")
        or keys.get("OPENROUTER_API_KEY")
        or keys.get("AZURE_API_KEY")
    )


def complete_text_for_model_config(
    session: Session,
    *,
    project_id: int,
    model_config_id: str,
    messages: list[dict[str, str]],
    timeout: float = 120.0,
    max_tokens: int | None = 512,
    temperature: float | None = 0.2,
    force_json_response: bool = False,
) -> LiteLLMCompletionResult:
    """Resolve catalog auth for a generative model and run one LiteLLM completion."""
    from backfield_ai.catalog_runtime import resolve_llm_auth_for_model_config

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
    assert_model_config_is_generative(cfg)

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
            "Azure OpenAI completions require an API base URL on the credential or host env.",
        )

    return completion_text_sync(
        litellm_model=lm,
        messages=messages,
        api_key=api_key,
        api_base=api_base,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        force_json_response=force_json_response,
    )
