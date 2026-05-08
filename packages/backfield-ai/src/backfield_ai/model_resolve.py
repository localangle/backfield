"""Resolve persisted AI model configs for runtime (GeocodeAgent, etc.)."""

from __future__ import annotations

from typing import Any

from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldProject,
)
from sqlmodel import Session, select

from backfield_ai.litellm_model import effective_litellm_model_row


def _load_enabled_org_config(
    session: Session,
    *,
    organization_id: int,
    project_id: int,
    config_id: str,
) -> BackfieldAiModelConfig:
    row = session.get(BackfieldAiModelConfig, config_id)
    if row is None or int(row.organization_id) != organization_id:
        raise ValueError("Model configuration not found for this project.")
    if str(row.status) != "active":
        raise ValueError("That model is disabled in the organization catalog.")
    ovr = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
            BackfieldAiProjectModelOverride.model_config_id == config_id,
        )
    ).first()
    if ovr is not None and not ovr.enabled:
        raise ValueError("That model is turned off for this project.")
    return row


def resolve_geocode_litellm_models(
    session: Session,
    project_id: int,
    params: Any,
) -> tuple[str, str, str]:
    """Return LiteLLM model ids for evaluation, router, and geographic-reasoning paths."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise ValueError("Project not found.")
    org_id = int(proj.organization_id)

    eval_id = getattr(params, "evaluationAiModelConfigId", None)
    router_id = getattr(params, "routerAiModelConfigId", None)
    geo_id = getattr(params, "geographicReasoningAiModelConfigId", None)
    eval_fallback = str(params.evaluationModel)
    router_fallback = str(params.routerModel)
    geo_fallback = str(getattr(params, "geographicReasoningModel", None) or "gpt-5-nano")

    if eval_id:
        cfg = _load_enabled_org_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(eval_id),
        )
        eval_fallback = effective_litellm_model_row(
            litellm_model=cfg.litellm_model,
            provider=str(cfg.provider),
            provider_model_id=str(cfg.provider_model_id),
        )
    if router_id:
        cfg_r = _load_enabled_org_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(router_id),
        )
        router_fallback = effective_litellm_model_row(
            litellm_model=cfg_r.litellm_model,
            provider=str(cfg_r.provider),
            provider_model_id=str(cfg_r.provider_model_id),
        )
    if geo_id:
        cfg_g = _load_enabled_org_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(geo_id),
        )
        geo_fallback = effective_litellm_model_row(
            litellm_model=cfg_g.litellm_model,
            provider=str(cfg_g.provider),
            provider_model_id=str(cfg_g.provider_model_id),
        )

    return eval_fallback, router_fallback, geo_fallback


def resolve_place_extract_litellm_model(
    session: Session,
    project_id: int,
    params: Any,
) -> str:
    """LiteLLM model id for PlaceExtract (catalog pin or legacy ``model`` string)."""
    fallback = str(getattr(params, "model", "") or "gpt-4o-mini")
    config_id = getattr(params, "aiModelConfigId", None)
    if not config_id:
        return fallback
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        return fallback
    org_id = int(proj.organization_id)
    cfg = _load_enabled_org_config(
        session,
        organization_id=org_id,
        project_id=project_id,
        config_id=str(config_id),
    )
    return effective_litellm_model_row(
        litellm_model=cfg.litellm_model,
        provider=str(cfg.provider),
        provider_model_id=str(cfg.provider_model_id),
    )
