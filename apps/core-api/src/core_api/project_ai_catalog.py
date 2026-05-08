"""Project-effective AI catalog: overrides, defaults, and listing helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_ai.constants import (
    PROJECT_AI_DEFAULT_ROLES,
    is_project_model_override_integration_key,
    project_model_override_integration_key,
)
from backfield_ai.litellm_model import effective_litellm_model_row
from backfield_db import (
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldOrganizationIntegrationSecret,
    BackfieldProject,
)
from backfield_db.crypto import encrypt_secret
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from core_api.ai_model_catalog import AiModelConfigOut, get_org_model_config, row_to_out
from core_api.org_integration_secrets import assert_encryption_usable


class ProjectEffectiveAiModelOut(AiModelConfigOut):
    """Organization catalog row as visible to this project."""

    project_enabled: bool = Field(
        description="False when the project explicitly hides this inherited model.",
    )
    project_credential_override_configured: bool = Field(
        default=False,
        description="True when this project stores its own API credential for this model.",
    )


class ProjectModelAvailabilityBody(BaseModel):
    enabled: bool


class ProjectModelCredentialOverrideBody(BaseModel):
    """Paste an API key used only when flows run in this project for this model."""

    api_key: str = Field(..., min_length=1)
    api_base: str | None = Field(
        default=None,
        description="Required for Azure OpenAI resources (resource endpoint URL).",
    )

    @field_validator("api_base", mode="before")
    @classmethod
    def strip_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class ProjectDefaultRoleAssignmentOut(BaseModel):
    role: str
    model_config_id: str


class ProjectDefaultRolePutBody(BaseModel):
    model_config_id: str = Field(..., min_length=1)


def _project_org_id(session: Session, project_id: int) -> int:
    p = session.get(BackfieldProject, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return int(p.organization_id)


def _effective_row_from_parts(
    cfg: BackfieldAiModelConfig,
    ovr: BackfieldAiProjectModelOverride | None,
) -> ProjectEffectiveAiModelOut:
    enabled = True if ovr is None else bool(ovr.enabled)
    has_override_cred = bool(ovr is not None and ovr.integration_secret_id is not None)
    base = row_to_out(cfg).model_dump()
    return ProjectEffectiveAiModelOut(
        **base,
        project_enabled=enabled,
        project_credential_override_configured=has_override_cred,
    )


def list_project_effective_models(
    session: Session,
    project_id: int,
    *,
    capabilities: list[str] | None = None,
    include_disabled: bool = False,
) -> list[ProjectEffectiveAiModelOut]:
    org_id = _project_org_id(session, project_id)
    configs = session.exec(
        select(BackfieldAiModelConfig)
        .where(
            BackfieldAiModelConfig.organization_id == org_id,
            col(BackfieldAiModelConfig.status) == "active",
            col(BackfieldAiModelConfig.model_kind) == "generative",
        )
        .order_by(col(BackfieldAiModelConfig.name))
    ).all()

    overrides = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
        )
    ).all()
    by_cfg = {str(o.model_config_id): o for o in overrides}

    cap_need = set(capabilities or [])
    out: list[ProjectEffectiveAiModelOut] = []
    for row in configs:
        cid = str(row.id)
        ovr = by_cfg.get(cid)
        enabled = True if ovr is None else bool(ovr.enabled)
        if not enabled and not include_disabled:
            continue
        caps = list(row.capabilities_json or [])
        if cap_need and not cap_need.issubset(set(caps)):
            continue
        out.append(_effective_row_from_parts(row, ovr))
    return out


def set_project_model_availability(
    session: Session,
    project_id: int,
    model_config_id: str,
    *,
    enabled: bool,
) -> ProjectEffectiveAiModelOut:
    org_id = _project_org_id(session, project_id)
    cfg = get_org_model_config(session, organization_id=org_id, config_id=model_config_id)

    existing = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
            BackfieldAiProjectModelOverride.model_config_id == model_config_id,
        )
    ).first()
    if existing:
        existing.enabled = enabled
        session.add(existing)
    else:
        session.add(
            BackfieldAiProjectModelOverride(
                project_id=project_id,
                model_config_id=model_config_id,
                enabled=enabled,
            )
        )
    session.commit()

    ovr = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
            BackfieldAiProjectModelOverride.model_config_id == model_config_id,
        )
    ).first()
    return _effective_row_from_parts(cfg, ovr)


def set_project_model_credential_override(
    session: Session,
    project_id: int,
    model_config_id: str,
    *,
    api_key: str,
    api_base: str | None,
) -> ProjectEffectiveAiModelOut:
    org_id = _project_org_id(session, project_id)
    cfg = get_org_model_config(session, organization_id=org_id, config_id=model_config_id)
    if str(cfg.status) != "active" or str(cfg.model_kind) != "generative":
        raise HTTPException(
            status_code=400,
            detail="Only active generative models support project credentials.",
        )

    lm = effective_litellm_model_row(
        litellm_model=cfg.litellm_model,
        provider=str(cfg.provider),
        provider_model_id=str(cfg.provider_model_id),
    )
    low_lm = lm.strip().lower()
    prov = str(cfg.provider).strip().lower()
    if prov == "azure" or low_lm.startswith("azure/"):
        if not (api_base or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Azure OpenAI requires a resource endpoint URL for this project.",
            )

    assert_encryption_usable()
    try:
        enc = encrypt_secret(api_key.strip())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    ik = project_model_override_integration_key(project_id, model_config_id)
    now = datetime.now(UTC)
    dn = f"Project · {cfg.name}"
    if len(dn) > 240:
        dn = dn[:240]

    existing_ov = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
            BackfieldAiProjectModelOverride.model_config_id == model_config_id,
        )
    ).first()
    if existing_ov is None:
        existing_ov = BackfieldAiProjectModelOverride(
            project_id=project_id,
            model_config_id=model_config_id,
            enabled=True,
        )
        session.add(existing_ov)
        session.flush()

    sec = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == org_id,
            BackfieldOrganizationIntegrationSecret.integration_key == ik,
        )
    ).first()
    ab = (api_base or "").strip() or None
    if sec:
        sec.value_encrypted = enc
        sec.api_base = ab
        sec.updated_at = now
        session.add(sec)
        session.flush()
        sid = sec.id
    else:
        row = BackfieldOrganizationIntegrationSecret(
            organization_id=org_id,
            integration_key=ik,
            credential_display_name=dn,
            api_base=ab,
            value_encrypted=enc,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        sid = row.id
    if sid is None:
        raise HTTPException(status_code=500, detail="Credential save failed")
    existing_ov.integration_secret_id = int(sid)
    session.add(existing_ov)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Could not save project credential.") from None

    session.refresh(existing_ov)
    return _effective_row_from_parts(cfg, existing_ov)


def clear_project_model_credential_override(
    session: Session,
    project_id: int,
    model_config_id: str,
) -> ProjectEffectiveAiModelOut:
    org_id = _project_org_id(session, project_id)
    cfg = get_org_model_config(session, organization_id=org_id, config_id=model_config_id)

    ovr = session.exec(
        select(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == project_id,
            BackfieldAiProjectModelOverride.model_config_id == model_config_id,
        )
    ).first()
    if ovr is None or ovr.integration_secret_id is None:
        return _effective_row_from_parts(cfg, ovr)

    sid = int(ovr.integration_secret_id)
    ovr.integration_secret_id = None
    session.add(ovr)
    session.flush()

    sec = session.get(BackfieldOrganizationIntegrationSecret, sid)
    if sec is not None and int(sec.organization_id) == org_id:
        if is_project_model_override_integration_key(str(sec.integration_key)):
            session.delete(sec)
    session.commit()
    session.refresh(ovr)
    return _effective_row_from_parts(cfg, ovr)


def list_project_default_roles(
    session: Session, project_id: int
) -> list[ProjectDefaultRoleAssignmentOut]:
    _project_org_id(session, project_id)
    rows = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.project_id == project_id,
            col(BackfieldAiDefaultModelRole.organization_id).is_(None),
        )
    ).all()
    return [
        ProjectDefaultRoleAssignmentOut(role=str(r.role), model_config_id=str(r.model_config_id))
        for r in sorted(rows, key=lambda x: x.role)
    ]


def put_project_default_role(
    session: Session,
    project_id: int,
    role: str,
    *,
    model_config_id: str,
) -> ProjectDefaultRoleAssignmentOut:
    org_id = _project_org_id(session, project_id)
    rkey = role.strip()
    if rkey not in PROJECT_AI_DEFAULT_ROLES:
        raise HTTPException(status_code=400, detail="Unsupported default role")
    get_org_model_config(session, organization_id=org_id, config_id=model_config_id)

    existing = session.exec(
        select(BackfieldAiDefaultModelRole).where(
            BackfieldAiDefaultModelRole.project_id == project_id,
            BackfieldAiDefaultModelRole.organization_id.is_(None),
            BackfieldAiDefaultModelRole.role == rkey,
        )
    ).first()
    if existing:
        existing.model_config_id = model_config_id
        session.add(existing)
    else:
        session.add(
            BackfieldAiDefaultModelRole(
                organization_id=None,
                project_id=project_id,
                role=rkey,
                model_config_id=model_config_id,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not save default role assignment",
        ) from None

    return ProjectDefaultRoleAssignmentOut(role=rkey, model_config_id=model_config_id)
