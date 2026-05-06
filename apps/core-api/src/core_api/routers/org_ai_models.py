"""Organization AI model catalog (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from core_api.ai_model_catalog import (
    AiModelConfigCreateBody,
    AiModelConfigOut,
    AiModelConfigPatchBody,
    CuratedAiModelOptionOut,
    create_org_model_config,
    delete_org_model_config,
    list_curated_options_out,
    list_org_model_configs,
    patch_org_model_config,
    run_org_model_connection_test,
)
from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session

router = APIRouter(prefix="/organizations", tags=["admin"])


@router.get("/{org_id}/ai-models/curated-options", response_model=list[CuratedAiModelOptionOut])
def get_ai_model_curated_options(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[CuratedAiModelOptionOut]:
    """Curated OpenAI and Anthropic presets for quick catalog setup."""
    require_org_admin(session, auth, org_id)
    return list_curated_options_out()


@router.get("/{org_id}/ai-models", response_model=list[AiModelConfigOut])
def list_organization_ai_models(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[AiModelConfigOut]:
    require_org_admin(session, auth, org_id)
    return list_org_model_configs(session, org_id)


@router.post("/{org_id}/ai-models", response_model=AiModelConfigOut)
def create_organization_ai_model(
    org_id: int,
    body: AiModelConfigCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> AiModelConfigOut:
    require_org_admin(session, auth, org_id)
    return create_org_model_config(session, org_id, body)


@router.patch("/{org_id}/ai-models/{config_id}", response_model=AiModelConfigOut)
def patch_organization_ai_model(
    org_id: int,
    config_id: str,
    body: AiModelConfigPatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> AiModelConfigOut:
    require_org_admin(session, auth, org_id)
    return patch_org_model_config(session, organization_id=org_id, config_id=config_id, body=body)


@router.delete("/{org_id}/ai-models/{config_id}", status_code=204)
def delete_organization_ai_model(
    org_id: int,
    config_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> None:
    require_org_admin(session, auth, org_id)
    delete_org_model_config(session, organization_id=org_id, config_id=config_id)


@router.post("/{org_id}/ai-models/{config_id}/test-connection", response_model=AiModelConfigOut)
def post_organization_ai_model_test_connection(
    org_id: int,
    config_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> AiModelConfigOut:
    """Ping provider through LiteLLM; updates latest test metadata only."""
    require_org_admin(session, auth, org_id)
    return run_org_model_connection_test(session, org_id, config_id)
