"""Resolve LLM API keys: project secrets override organization integration secrets."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganizationIntegrationSecret,
    BackfieldProject,
    BackfieldProjectSecret,
)
from backfield_db.crypto import decrypt_secret, fernet_from_env
from sqlmodel import Session, col, select

from backfield_ai.constants import (
    INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
    INTEGRATION_KEY_AI_PROVIDER_AZURE,
    INTEGRATION_KEY_AI_PROVIDER_GEMINI,
    INTEGRATION_KEY_AI_PROVIDER_OPENAI,
    INTEGRATION_KEY_AI_PROVIDER_OPENROUTER,
    INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH,
    INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH,
    INTEGRATION_KEY_PLATFORM_GEOCODIO,
    INTEGRATION_KEY_PLATFORM_S3_ACCESS_KEY_ID,
    INTEGRATION_KEY_PLATFORM_S3_SECRET_ACCESS_KEY,
    INTEGRATION_KEY_PLATFORM_S3_SESSION_TOKEN,
    ORG_PLATFORM_INTEGRATION_KEYS,
)


def organization_llm_api_keys(session: Session, organization_id: int) -> dict[str, str]:
    """LLM-related organization integration secrets (API keys)."""
    if fernet_from_env() is None:
        return {}
    org_keys = (
        INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
        INTEGRATION_KEY_AI_PROVIDER_GEMINI,
        INTEGRATION_KEY_AI_PROVIDER_OPENROUTER,
        INTEGRATION_KEY_AI_PROVIDER_AZURE,
    )
    out: dict[str, str] = {}
    org_rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            col(BackfieldOrganizationIntegrationSecret.integration_key).in_(org_keys),
        )
    ).all()
    for row in org_rows:
        try:
            plain = decrypt_secret(row.value_encrypted)
        except Exception:
            continue
        if row.integration_key == INTEGRATION_KEY_AI_PROVIDER_OPENAI:
            out["OPENAI_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC:
            out["ANTHROPIC_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_GEMINI:
            out["GEMINI_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_OPENROUTER:
            out["OPENROUTER_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_AZURE:
            out["AZURE_API_KEY"] = plain
    return out


def organization_platform_env_keys(session: Session, organization_id: int) -> dict[str, str]:
    """Map organization platform integration secrets to worker env names."""
    if fernet_from_env() is None:
        return {}
    rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            col(BackfieldOrganizationIntegrationSecret.integration_key).in_(ORG_PLATFORM_INTEGRATION_KEYS),
        )
    ).all()
    out: dict[str, str] = {}
    for row in rows:
        try:
            plain = decrypt_secret(row.value_encrypted)
        except Exception:
            continue
        ik = str(row.integration_key)
        if ik == INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH:
            out["PELIAS_API_KEY"] = plain
        elif ik == INTEGRATION_KEY_PLATFORM_GEOCODIO:
            out["GEOCODIO_API_KEY"] = plain
        elif ik == INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH:
            out["BRAVE_SEARCH_API_KEY"] = plain
        elif ik == INTEGRATION_KEY_PLATFORM_S3_ACCESS_KEY_ID:
            out["AWS_ACCESS_KEY_ID"] = plain
        elif ik == INTEGRATION_KEY_PLATFORM_S3_SECRET_ACCESS_KEY:
            out["AWS_SECRET_ACCESS_KEY"] = plain
        elif ik == INTEGRATION_KEY_PLATFORM_S3_SESSION_TOKEN:
            out["AWS_SESSION_TOKEN"] = plain
    return out


def merge_project_and_org_llm_api_keys(session: Session, project_id: int) -> dict[str, str]:
    """Return env-style map (``OPENAI_API_KEY``, ``AZURE_API_BASE``, …).

    Organization integration secrets provide defaults; project secrets overwrite.
    """
    if fernet_from_env() is None:
        return {}

    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        return {}

    org_id = int(proj.organization_id)
    out: dict[str, str] = {}

    org_keys = (
        INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
        INTEGRATION_KEY_AI_PROVIDER_GEMINI,
        INTEGRATION_KEY_AI_PROVIDER_OPENROUTER,
        INTEGRATION_KEY_AI_PROVIDER_AZURE,
    )
    org_rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == org_id,
            col(BackfieldOrganizationIntegrationSecret.integration_key).in_(org_keys),
        )
    ).all()
    for row in org_rows:
        try:
            plain = decrypt_secret(row.value_encrypted)
        except Exception:
            continue
        if row.integration_key == INTEGRATION_KEY_AI_PROVIDER_OPENAI:
            out["OPENAI_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC:
            out["ANTHROPIC_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_GEMINI:
            out["GEMINI_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_OPENROUTER:
            out["OPENROUTER_API_KEY"] = plain
        elif row.integration_key == INTEGRATION_KEY_AI_PROVIDER_AZURE:
            out["AZURE_API_KEY"] = plain

    for env_key, val in organization_platform_env_keys(session, org_id).items():
        out[env_key] = val

    proj_rows = session.exec(
        select(BackfieldProjectSecret).where(BackfieldProjectSecret.project_id == project_id)
    ).all()
    for row in proj_rows:
        try:
            out[row.key] = decrypt_secret(row.value_encrypted)
        except Exception:
            continue

    return out
