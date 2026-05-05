"""Organization integration secrets: encrypted storage and AI provider catalog helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_ai.constants import (
    AI_PROVIDER_SLUG_BY_INTEGRATION_KEY,
    ORG_AI_PROVIDER_INTEGRATION_KEYS,
)
from backfield_db import BackfieldOrganizationIntegrationSecret
from backfield_db.crypto import encrypt_secret, fernet_from_env
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select


class IntegrationSecretOut(BaseModel):
    """Metadata only — ciphertext is never exposed."""

    integration_key: str
    created_at: datetime
    updated_at: datetime


class IntegrationSecretSetBody(BaseModel):
    value: str = Field(..., min_length=1)


class AiProviderIntegrationCatalogEntryOut(BaseModel):
    provider: str
    integration_key: str
    configured: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


def assert_encryption_usable() -> None:
    if fernet_from_env() is None:
        raise HTTPException(
            status_code=503,
            detail="MASTER_ENCRYPTION_KEY is not configured; cannot store secrets",
        )


def integration_keys_loaded(
    session: Session, organization_id: int
) -> dict[str, BackfieldOrganizationIntegrationSecret]:
    rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            col(BackfieldOrganizationIntegrationSecret.integration_key).in_(ORG_AI_PROVIDER_INTEGRATION_KEYS),
        )
    ).all()
    return {r.integration_key: r for r in rows}


def list_ai_provider_catalog_entries(
    session: Session, organization_id: int
) -> list[AiProviderIntegrationCatalogEntryOut]:
    by_key = integration_keys_loaded(session, organization_id)
    out: list[AiProviderIntegrationCatalogEntryOut] = []
    for key in sorted(ORG_AI_PROVIDER_INTEGRATION_KEYS):
        slug = AI_PROVIDER_SLUG_BY_INTEGRATION_KEY[key]
        row = by_key.get(key)
        out.append(
            AiProviderIntegrationCatalogEntryOut(
                provider=slug,
                integration_key=key,
                configured=row is not None,
                created_at=row.created_at if row else None,
                updated_at=row.updated_at if row else None,
            )
        )
    return out


def list_org_integration_secret_metadata(
    session: Session, organization_id: int
) -> list[IntegrationSecretOut]:
    rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret)
        .where(BackfieldOrganizationIntegrationSecret.organization_id == organization_id)
        .order_by(col(BackfieldOrganizationIntegrationSecret.integration_key))
    ).all()
    return [
        IntegrationSecretOut(
            integration_key=r.integration_key,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def upsert_org_integration_secret(
    session: Session,
    organization_id: int,
    integration_key: str,
    plain_value: str,
) -> IntegrationSecretOut:
    if integration_key not in ORG_AI_PROVIDER_INTEGRATION_KEYS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported integration_key for organization secrets",
        )
    assert_encryption_usable()
    try:
        enc = encrypt_secret(plain_value)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    now = datetime.now(UTC)
    existing = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            BackfieldOrganizationIntegrationSecret.integration_key == integration_key,
        )
    ).first()
    if existing:
        existing.value_encrypted = enc
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return IntegrationSecretOut(
            integration_key=existing.integration_key,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    row = BackfieldOrganizationIntegrationSecret(
        organization_id=organization_id,
        integration_key=integration_key,
        value_encrypted=enc,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return IntegrationSecretOut(
        integration_key=row.integration_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def delete_org_integration_secret(
    session: Session, organization_id: int, integration_key: str
) -> None:
    if integration_key not in ORG_AI_PROVIDER_INTEGRATION_KEYS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported integration_key for organization secrets",
        )
    row = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            BackfieldOrganizationIntegrationSecret.integration_key == integration_key,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    session.delete(row)
    session.commit()
