"""Runtime auth + LiteLLM route resolution for catalog-backed models (worker execution)."""

from __future__ import annotations

from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganizationIntegrationSecret,
    BackfieldProject,
)
from backfield_db.crypto import decrypt_secret
from sqlmodel import Session

from backfield_ai.litellm_model import effective_litellm_model_row


def resolve_llm_auth_for_model_config(
    session: Session,
    *,
    project_id: int,
    model_config_id: str | None,
    fallback_litellm_model: str,
) -> tuple[str, str | None, str | None]:
    """Return ``(litellm_model, api_key_or_none, api_base_or_none)``.

    When ``api_key_or_none`` is set, callers must use it (and optional ``api_base``) instead of
    organization default keys. When unset, keep existing provider-based key selection from env.
    """
    mc = (model_config_id or "").strip() or None
    fb = fallback_litellm_model.strip()
    if not mc:
        return fb, None, None

    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        return fb, None, None

    org_id = int(proj.organization_id)
    cfg = session.get(BackfieldAiModelConfig, mc)
    if cfg is None or int(cfg.organization_id) != org_id:
        return fb, None, None

    lm = effective_litellm_model_row(
        litellm_model=cfg.litellm_model,
        provider=str(cfg.provider),
        provider_model_id=str(cfg.provider_model_id),
    )
    sid = cfg.integration_secret_id
    if sid is None:
        return lm, None, None

    cred = session.get(BackfieldOrganizationIntegrationSecret, int(sid))
    if cred is None or int(cred.organization_id) != org_id:
        raise ValueError(
            "API credential for this model is missing or belongs to another organization.",
        )
    try:
        plain = decrypt_secret(cred.value_encrypted)
    except Exception as exc:
        raise ValueError("Could not decrypt stored API credential for this model.") from exc
    if not plain.strip():
        raise ValueError("Stored API credential for this model is empty.")
    api_base = (cred.api_base or "").strip() or None
    return lm, plain.strip(), api_base
