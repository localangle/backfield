"""Organization integration secrets (org admin; ciphertext never returned)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session
from core_api.org_integration_secrets import (
    AiCredentialCatalogEntryOut,
    AiProviderIntegrationCatalogEntryOut,
    IntegrationSecretCreateBody,
    IntegrationSecretCreatedOut,
    IntegrationSecretOut,
    IntegrationSecretPatchBody,
    IntegrationSecretSetBody,
    create_org_integration_credential,
    delete_org_integration_secret,
    list_ai_credentials_catalog_entries,
    list_ai_provider_catalog_entries,
    list_org_integration_secret_metadata,
    patch_org_integration_secret,
    upsert_org_integration_secret,
)

router = APIRouter(prefix="/organizations", tags=["admin"])


@router.get(
    "/{org_id}/integration-secrets/catalog",
    response_model=list[AiCredentialCatalogEntryOut],
)
def get_organization_integration_secrets_catalog(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[AiCredentialCatalogEntryOut]:
    """Preset slots plus saved custom credentials (metadata only)."""
    require_org_admin(session, auth, org_id)
    return list_ai_credentials_catalog_entries(session, org_id)


@router.get(
    "/{org_id}/integration-secrets/ai-provider-catalog",
    response_model=list[AiProviderIntegrationCatalogEntryOut],
)
def get_ai_provider_integration_catalog(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[AiProviderIntegrationCatalogEntryOut]:
    """Built-in vendor slots only (legacy shape)."""
    require_org_admin(session, auth, org_id)
    return list_ai_provider_catalog_entries(session, org_id)


@router.get("/{org_id}/integration-secrets", response_model=list[IntegrationSecretOut])
def list_organization_integration_secrets(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[IntegrationSecretOut]:
    """Stored organization secrets — metadata only."""
    require_org_admin(session, auth, org_id)
    return list_org_integration_secret_metadata(session, org_id)


@router.post(
    "/{org_id}/integration-secrets",
    response_model=IntegrationSecretCreatedOut,
)
def post_organization_integration_secret(
    org_id: int,
    body: IntegrationSecretCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> IntegrationSecretCreatedOut:
    """Create a new arbitrary vendor credential (no preset slot)."""
    require_org_admin(session, auth, org_id)
    return create_org_integration_credential(session, org_id, body)


@router.put("/{org_id}/integration-secrets/{integration_key}", response_model=IntegrationSecretOut)
def put_organization_integration_secret(
    org_id: int,
    integration_key: str,
    body: IntegrationSecretSetBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> IntegrationSecretOut:
    require_org_admin(session, auth, org_id)
    return upsert_org_integration_secret(
        session,
        org_id,
        integration_key,
        body.value,
        display_name=body.display_name,
        api_base=body.api_base,
    )


@router.patch(
    "/{org_id}/integration-secrets/{integration_key}",
    response_model=IntegrationSecretOut,
)
def patch_organization_integration_secret(
    org_id: int,
    integration_key: str,
    body: IntegrationSecretPatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> IntegrationSecretOut:
    require_org_admin(session, auth, org_id)
    return patch_org_integration_secret(session, org_id, integration_key, body)


@router.delete("/{org_id}/integration-secrets/{integration_key}", status_code=204)
def delete_organization_integration_secret(
    org_id: int,
    integration_key: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> None:
    require_org_admin(session, auth, org_id)
    delete_org_integration_secret(session, org_id, integration_key)
