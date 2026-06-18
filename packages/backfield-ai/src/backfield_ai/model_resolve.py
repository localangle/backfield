"""Resolve persisted AI model configs for runtime (GeocodeAgent, etc.)."""

from __future__ import annotations

from typing import Any

from backfield_db import (
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldProject,
)
from sqlmodel import Session, select

from backfield_ai.constants import (
    AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
    AI_DEFAULT_ROLE_SEMANTIC_HYDE,
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
)
from backfield_ai.embeddings import EmbeddingConfigurationError
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
) -> tuple[str, str, str, str]:
    """Return LiteLLM model ids for evaluation, router, reasoning, and estimation paths."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise ValueError("Project not found.")
    org_id = int(proj.organization_id)

    eval_id = getattr(params, "evaluationAiModelConfigId", None)
    router_id = getattr(params, "routerAiModelConfigId", None)
    geo_id = getattr(params, "geographicReasoningAiModelConfigId", None)
    est_id = getattr(params, "geographicEstimationAiModelConfigId", None)
    eval_fallback = str(params.evaluationModel)
    router_fallback = str(params.routerModel)
    geo_fallback = str(getattr(params, "geographicReasoningModel", None) or "gpt-5-nano")
    est_fallback = str(getattr(params, "geographicEstimationModel", None) or "").strip()

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
    if est_id:
        cfg_e = _load_enabled_org_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(est_id),
        )
        est_fallback = effective_litellm_model_row(
            litellm_model=cfg_e.litellm_model,
            provider=str(cfg_e.provider),
            provider_model_id=str(cfg_e.provider_model_id),
        )
    elif not est_fallback:
        est_fallback = geo_fallback

    return eval_fallback, router_fallback, geo_fallback, est_fallback


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


def _enabled_embedding_config_ids(session: Session, project_id: int) -> list[str]:
    """Embedding catalog rows that are active org-wide and enabled for this project."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        return []
    org_id = int(proj.organization_id)
    configs = list(
        session.exec(
            select(BackfieldAiModelConfig).where(
                BackfieldAiModelConfig.organization_id == org_id,
                BackfieldAiModelConfig.status == "active",
                BackfieldAiModelConfig.model_kind == AI_MODEL_KIND_EMBEDDING,
            )
        ).all()
    )
    if not configs:
        return []
    overrides = {
        str(o.model_config_id): o
        for o in session.exec(
            select(BackfieldAiProjectModelOverride).where(
                BackfieldAiProjectModelOverride.project_id == project_id,
            )
        ).all()
    }
    enabled: list[str] = []
    for row in configs:
        cid = str(row.id)
        ovr = overrides.get(cid)
        if ovr is not None and not ovr.enabled:
            continue
        enabled.append(cid)
    return enabled


def _try_load_semantic_embedding_config(
    session: Session,
    *,
    organization_id: int,
    project_id: int,
    config_id: str,
) -> str | None:
    try:
        _load_enabled_org_config(
            session,
            organization_id=organization_id,
            project_id=project_id,
            config_id=config_id,
        )
    except ValueError:
        return None
    return config_id


def resolve_semantic_embedding_model_config_id(
    session: Session,
    project_id: int,
) -> str:
    """Resolve the embedding model for semantic indexing (default role or sole enabled model)."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise EmbeddingConfigurationError("Project not found.")
    org_id = int(proj.organization_id)

    project_role = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.project_id == project_id,
            BackfieldAiDefaultModelRole.organization_id.is_(None),
            BackfieldAiDefaultModelRole.role == AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
        )
    ).first()
    if project_role is not None:
        loaded = _try_load_semantic_embedding_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(project_role.model_config_id),
        )
        if loaded is not None:
            return loaded

    org_role = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.organization_id == org_id,
            BackfieldAiDefaultModelRole.project_id.is_(None),
            BackfieldAiDefaultModelRole.role == AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
        )
    ).first()
    if org_role is not None:
        loaded = _try_load_semantic_embedding_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(org_role.model_config_id),
        )
        if loaded is not None:
            return loaded

    enabled = _enabled_embedding_config_ids(session, project_id)
    if len(enabled) == 1:
        return enabled[0]
    if not enabled:
        raise EmbeddingConfigurationError(
            "No embedding model configured. Enable an embedding model for this project "
            "and set a default for semantic indexing.",
        )
    raise EmbeddingConfigurationError(
        "Multiple embedding models are enabled for this project. Set a default for "
        "semantic indexing on the project Models tab.",
    )


def semantic_embedding_configured(session: Session, project_id: int) -> bool:
    """True when semantic indexing can resolve an enabled embedding model for the project."""
    try:
        resolve_semantic_embedding_model_config_id(session, project_id)
        return True
    except EmbeddingConfigurationError:
        return False


def _enabled_generative_config_ids(session: Session, project_id: int) -> list[str]:
    """Generative catalog rows that are active org-wide and enabled for this project."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        return []
    org_id = int(proj.organization_id)
    configs = list(
        session.exec(
            select(BackfieldAiModelConfig).where(
                BackfieldAiModelConfig.organization_id == org_id,
                BackfieldAiModelConfig.status == "active",
                BackfieldAiModelConfig.model_kind == AI_MODEL_KIND_GENERATIVE,
            )
        ).all()
    )
    if not configs:
        return []
    overrides = {
        str(o.model_config_id): o
        for o in session.exec(
            select(BackfieldAiProjectModelOverride).where(
                BackfieldAiProjectModelOverride.project_id == project_id,
            )
        ).all()
    }
    enabled: list[str] = []
    for row in configs:
        cid = str(row.id)
        ovr = overrides.get(cid)
        if ovr is not None and not ovr.enabled:
            continue
        enabled.append(cid)
    return enabled


def _try_load_semantic_generative_config(
    session: Session,
    *,
    organization_id: int,
    project_id: int,
    config_id: str,
) -> str | None:
    try:
        cfg = _load_enabled_org_config(
            session,
            organization_id=organization_id,
            project_id=project_id,
            config_id=config_id,
        )
    except ValueError:
        return None
    if str(cfg.model_kind) != AI_MODEL_KIND_GENERATIVE:
        return None
    return config_id


def resolve_semantic_hyde_model_config_id(
    session: Session,
    project_id: int,
) -> str:
    """Resolve the generative model for HyDE query expansion."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise EmbeddingConfigurationError("Project not found.")
    org_id = int(proj.organization_id)

    project_role = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.project_id == project_id,
            BackfieldAiDefaultModelRole.organization_id.is_(None),
            BackfieldAiDefaultModelRole.role == AI_DEFAULT_ROLE_SEMANTIC_HYDE,
        )
    ).first()
    if project_role is not None:
        loaded = _try_load_semantic_generative_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(project_role.model_config_id),
        )
        if loaded is not None:
            return loaded

    org_role = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.organization_id == org_id,
            BackfieldAiDefaultModelRole.project_id.is_(None),
            BackfieldAiDefaultModelRole.role == AI_DEFAULT_ROLE_SEMANTIC_HYDE,
        )
    ).first()
    if org_role is not None:
        loaded = _try_load_semantic_generative_config(
            session,
            organization_id=org_id,
            project_id=project_id,
            config_id=str(org_role.model_config_id),
        )
        if loaded is not None:
            return loaded

    enabled = _enabled_generative_config_ids(session, project_id)
    if len(enabled) == 1:
        return enabled[0]
    if not enabled:
        raise EmbeddingConfigurationError(
            "No generative model configured. Enable a generative model for this project "
            "and set a default for semantic HyDE, or enable exactly one generative model.",
        )
    raise EmbeddingConfigurationError(
        "Multiple generative models are enabled for this project. Set a default for "
        "semantic HyDE on the project Models tab.",
    )
