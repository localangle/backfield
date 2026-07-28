"""Shared LLM credential resolution for Stylebook cleanup worker jobs."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_ai.catalog_runtime import resolve_llm_auth_for_model_config
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.litellm_model import effective_litellm_model_row
from backfield_db import BackfieldAiModelConfig, BackfieldProject
from sqlmodel import Session, select


@dataclass(frozen=True)
class CleanupLlmAuthContext:
    project_id: int
    api_key_overlay: dict[str, str]
    model: str
    model_config_id: str | None


def overlay_catalog_auth(
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


def resolve_organization_cleanup_project_id(session: Session, *, organization_id: int) -> int:
    """Pick a project used to resolve org AI credentials."""
    project_ids = session.exec(
        select(BackfieldProject.id)
        .where(BackfieldProject.organization_id == int(organization_id))
        .order_by(BackfieldProject.id)
    ).all()
    if not project_ids:
        raise ValueError(
            "No projects found for this organization; cannot resolve AI credentials."
        )
    return int(project_ids[0])


def resolve_cleanup_llm_auth(
    session: Session,
    *,
    organization_id: int,
    provider_model_id: str | None,
    ai_model_config_id: str | None,
    default_model: str,
) -> CleanupLlmAuthContext:
    """Resolve provider API keys from org/project secrets and optional model config."""
    project_id = resolve_organization_cleanup_project_id(
        session, organization_id=organization_id
    )
    project = session.get(BackfieldProject, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found.")

    model = (provider_model_id or "").strip() or default_model
    model_config_id = (ai_model_config_id or "").strip() or None
    overlay = merge_project_and_org_llm_api_keys(session, project_id)

    if model_config_id:
        cfg = session.get(BackfieldAiModelConfig, model_config_id)
        if cfg is None or int(cfg.organization_id) != int(organization_id):
            raise ValueError(
                "Selected AI model is missing or belongs to another organization."
            )
        model = str(cfg.provider_model_id or model).strip() or default_model
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
        overlay = overlay_catalog_auth(
            overlay,
            provider=str(cfg.provider),
            api_key=catalog_key,
            api_base=api_base,
        )

    llm_kwargs = call_llm_kwargs_from_overlay(overlay)
    if not llm_kwargs:
        raise ValueError(
            "No provider credentials configured for this organization. "
            "Add AI credentials in organization settings before running this review."
        )

    return CleanupLlmAuthContext(
        project_id=project_id,
        api_key_overlay=overlay,
        model=model,
        model_config_id=model_config_id,
    )


def call_llm_kwargs_from_overlay(overlay: dict[str, str]) -> dict[str, str]:
    """Map env-style overlay keys to ``call_llm`` keyword arguments."""
    kwargs: dict[str, str] = {}
    if overlay.get("OPENAI_API_KEY"):
        kwargs["openai_api_key"] = overlay["OPENAI_API_KEY"]
    if overlay.get("ANTHROPIC_API_KEY"):
        kwargs["anthropic_api_key"] = overlay["ANTHROPIC_API_KEY"]
    if overlay.get("GEMINI_API_KEY"):
        kwargs["gemini_api_key"] = overlay["GEMINI_API_KEY"]
    if overlay.get("OPENROUTER_API_KEY"):
        kwargs["openrouter_api_key"] = overlay["OPENROUTER_API_KEY"]
    if overlay.get("AZURE_API_KEY"):
        kwargs["azure_api_key"] = overlay["AZURE_API_KEY"]
    if overlay.get("AZURE_API_BASE"):
        kwargs["azure_api_base"] = overlay["AZURE_API_BASE"]
    return kwargs


def is_llm_auth_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if "auth" in name or "permission" in name:
        return True
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "api key",
                "api_key",
                "credential",
                "credentials",
                "authentication",
                "unauthorized",
                "configure in project settings",
                "organization settings",
            )
        )
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "invalid_api_key",
            "incorrect api key",
            "authentication",
            "unauthorized",
            "401",
            "403",
        )
    )
