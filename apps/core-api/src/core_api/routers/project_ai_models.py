"""Project-effective AI catalog (requires project access)."""

from __future__ import annotations

from backfield_ai.model_resolve import semantic_embedding_configured
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from core_api.authz import require_project_access
from core_api.deps import get_auth, get_session
from core_api.project_ai_catalog import (
    ProjectDefaultRoleAssignmentOut,
    ProjectDefaultRolePutBody,
    ProjectEffectiveAiModelOut,
    ProjectModelAvailabilityBody,
    ProjectModelCredentialOverrideBody,
    clear_project_model_credential_override,
    list_project_default_roles,
    list_project_effective_models,
    put_project_default_role,
    set_project_model_availability,
    set_project_model_credential_override,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class SemanticIndexingConfiguredOut(BaseModel):
    configured: bool


@router.get(
    "/{project_id}/semantic-indexing-configured",
    response_model=SemanticIndexingConfiguredOut,
)
def get_project_semantic_indexing_configured(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> SemanticIndexingConfiguredOut:
    require_project_access(session, auth, project_id)
    return SemanticIndexingConfiguredOut(
        configured=semantic_embedding_configured(session, project_id),
    )


@router.get("/{project_id}/ai-models/effective", response_model=list[ProjectEffectiveAiModelOut])
def get_project_effective_ai_models(
    project_id: int,
    capabilities: str | None = Query(
        default=None,
        description="Comma-separated capability filter (all must be present), e.g. text,json",
    ),
    include_disabled: bool = Query(
        default=False,
        description="Include models turned off for this project (workspace Models UI).",
    ),
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[ProjectEffectiveAiModelOut]:
    require_project_access(session, auth, project_id)
    cap_list = None
    if capabilities:
        cap_list = [c.strip() for c in capabilities.split(",") if c.strip()]
    return list_project_effective_models(
        session,
        project_id,
        capabilities=cap_list,
        include_disabled=include_disabled,
    )


@router.put(
    "/{project_id}/ai-models/{model_config_id}/availability",
    response_model=ProjectEffectiveAiModelOut,
)
def put_project_ai_model_availability(
    project_id: int,
    model_config_id: str,
    body: ProjectModelAvailabilityBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> ProjectEffectiveAiModelOut:
    require_project_access(session, auth, project_id)
    return set_project_model_availability(
        session,
        project_id,
        model_config_id,
        enabled=body.enabled,
    )


@router.put(
    "/{project_id}/ai-models/{model_config_id}/credential-override",
    response_model=ProjectEffectiveAiModelOut,
)
def put_project_ai_model_credential_override(
    project_id: int,
    model_config_id: str,
    body: ProjectModelCredentialOverrideBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> ProjectEffectiveAiModelOut:
    require_project_access(session, auth, project_id)
    return set_project_model_credential_override(
        session,
        project_id,
        model_config_id,
        api_key=body.api_key,
        api_base=body.api_base,
    )


@router.delete(
    "/{project_id}/ai-models/{model_config_id}/credential-override",
    response_model=ProjectEffectiveAiModelOut,
)
def delete_project_ai_model_credential_override(
    project_id: int,
    model_config_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> ProjectEffectiveAiModelOut:
    require_project_access(session, auth, project_id)
    return clear_project_model_credential_override(session, project_id, model_config_id)


@router.get("/{project_id}/ai-model-defaults", response_model=list[ProjectDefaultRoleAssignmentOut])
def get_project_ai_model_defaults(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[ProjectDefaultRoleAssignmentOut]:
    require_project_access(session, auth, project_id)
    return list_project_default_roles(session, project_id)


@router.put(
    "/{project_id}/ai-model-defaults/{role}",
    response_model=ProjectDefaultRoleAssignmentOut,
)
def put_project_ai_model_default_for_role(
    project_id: int,
    role: str,
    body: ProjectDefaultRolePutBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> ProjectDefaultRoleAssignmentOut:
    require_project_access(session, auth, project_id)
    return put_project_default_role(
        session,
        project_id,
        role,
        model_config_id=body.model_config_id,
    )
