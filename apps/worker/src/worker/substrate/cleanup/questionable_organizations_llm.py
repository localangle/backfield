"""LLM auth/model resolution for questionable organization cleanup runs."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_ai.catalog_runtime import resolve_llm_auth_for_model_config
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.litellm_model import effective_litellm_model_row
from backfield_ai.model_resolve import resolve_generative_default_model_config_id
from backfield_db import BackfieldAiModelConfig, BackfieldProject
from backfield_entities.quality.check_runs import CleanupRunScope
from backfield_entities.quality.finders._questionable_organization_evidence import (
    organization_project_ids,
)
from backfield_entities.quality.llm_questionable_organizations import (
    DEFAULT_QUESTIONABLE_ORG_LLM_MODEL,
)
from sqlmodel import Session


@dataclass(frozen=True)
class QuestionableOrganizationLlmContext:
    project_id: int
    api_key_overlay: dict[str, str]
    model: str
    model_config_id: str


def _overlay_catalog_auth(
    overlay: dict[str, str],
    *,
    provider: str,
    api_key: str | None,
    api_base: str | None,
) -> dict[str, str]:
    merged = dict(overlay)
    if api_key:
        provider_key = provider.strip().lower()
        if provider_key == "openai":
            merged["OPENAI_API_KEY"] = api_key
        elif provider_key == "anthropic":
            merged["ANTHROPIC_API_KEY"] = api_key
        elif provider_key == "gemini":
            merged["GEMINI_API_KEY"] = api_key
        elif provider_key == "openrouter":
            merged["OPENROUTER_API_KEY"] = api_key
        elif provider_key == "azure":
            merged["AZURE_API_KEY"] = api_key
    if api_base:
        merged["AZURE_API_BASE"] = api_base
    return merged


def resolve_cleanup_project_id(session: Session, *, scope: CleanupRunScope) -> int:
    """Pick a project used to resolve org AI credentials and default models."""
    if scope.project_ids:
        return int(scope.project_ids[0])
    project_ids = organization_project_ids(session, organization_id=scope.organization_id)
    if not project_ids:
        raise ValueError(
            "No projects found for this organization; cannot run questionable organization review."
        )
    return int(project_ids[0])


def resolve_questionable_organization_llm_context(
    session: Session,
    *,
    scope: CleanupRunScope,
) -> QuestionableOrganizationLlmContext:
    project_id = resolve_cleanup_project_id(session, scope=scope)
    project = session.get(BackfieldProject, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found.")

    try:
        model_config_id = resolve_generative_default_model_config_id(session, project_id)
    except EmbeddingConfigurationError as exc:
        raise ValueError(str(exc)) from exc

    cfg = session.get(BackfieldAiModelConfig, model_config_id)
    if cfg is None:
        raise ValueError("Configured generative model not found.")

    provider_model = str(cfg.provider_model_id or DEFAULT_QUESTIONABLE_ORG_LLM_MODEL).strip()
    overlay = merge_project_and_org_llm_api_keys(session, project_id)
    _lm, catalog_key, api_base = resolve_llm_auth_for_model_config(
        session,
        project_id=project_id,
        model_config_id=model_config_id,
        fallback_litellm_model=effective_litellm_model_row(
            litellm_model=cfg.litellm_model,
            provider=str(cfg.provider),
            provider_model_id=str(cfg.provider_model_id),
        ),
    )
    overlay = _overlay_catalog_auth(
        overlay,
        provider=str(cfg.provider),
        api_key=catalog_key,
        api_base=api_base,
    )
    if not overlay:
        raise ValueError(
            "No provider credentials configured for this organization. "
            "Add AI credentials in organization settings before running this check."
        )

    return QuestionableOrganizationLlmContext(
        project_id=project_id,
        api_key_overlay=overlay,
        model=provider_model,
        model_config_id=str(model_config_id),
    )
