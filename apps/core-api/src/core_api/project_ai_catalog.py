"""Project-effective AI catalog: overrides, defaults, and listing helpers."""

from __future__ import annotations

from backfield_ai.constants import PROJECT_AI_DEFAULT_ROLES
from backfield_db import (
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldProject,
)
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from core_api.ai_model_catalog import AiModelConfigOut, get_org_model_config, row_to_out


class ProjectEffectiveAiModelOut(AiModelConfigOut):
    """Organization catalog row as visible to this project."""

    project_enabled: bool = Field(
        description="False when the project explicitly hides this inherited model.",
    )


class ProjectModelAvailabilityBody(BaseModel):
    enabled: bool


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


def list_project_effective_models(
    session: Session,
    project_id: int,
    *,
    capabilities: list[str] | None = None,
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
        if not enabled:
            continue
        caps = list(row.capabilities_json or [])
        if cap_need and not cap_need.issubset(set(caps)):
            continue
        base = row_to_out(row).model_dump()
        out.append(ProjectEffectiveAiModelOut(**base, project_enabled=enabled))
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
    eff_enabled = True if ovr is None else bool(ovr.enabled)
    base = row_to_out(cfg).model_dump()
    return ProjectEffectiveAiModelOut(**base, project_enabled=eff_enabled)


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

