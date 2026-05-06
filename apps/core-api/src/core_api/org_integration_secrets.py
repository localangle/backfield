"""Organization integration secrets: encrypted storage and unified AI credential catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from backfield_ai.constants import (
    AI_PROVIDER_SLUG_BY_INTEGRATION_KEY,
    INTEGRATION_KEY_AI_CREDENTIAL_PREFIX,
    ORG_AI_PROVIDER_INTEGRATION_KEYS,
    is_built_in_ai_provider_integration_key,
    is_custom_ai_credential_integration_key,
)
from backfield_db import BackfieldAiModelConfig, BackfieldOrganizationIntegrationSecret
from backfield_db.crypto import encrypt_secret, fernet_from_env
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session, col, select


class IntegrationSecretOut(BaseModel):
    """Metadata only — ciphertext is never exposed."""

    integration_secret_id: int | None = None
    integration_key: str
    created_at: datetime
    updated_at: datetime


class IntegrationSecretSetBody(BaseModel):
    value: str = Field(..., min_length=1)
    display_name: str | None = Field(default=None, max_length=240)
    api_base: str | None = Field(default=None, max_length=2048)

    @field_validator("display_name", "api_base", mode="before")
    @classmethod
    def strip_blank_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class IntegrationSecretPatchBody(BaseModel):
    value: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, max_length=240)
    api_base: str | None = Field(default=None, max_length=2048)

    @field_validator("display_name", "api_base", mode="before")
    @classmethod
    def strip_blank_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @model_validator(mode="after")
    def require_some_field(self) -> IntegrationSecretPatchBody:
        data = self.model_dump(exclude_unset=True)
        if not data:
            raise ValueError("No fields to update")
        return self


class IntegrationSecretCreateBody(BaseModel):
    """Create an arbitrary vendor credential (same storage as preset provider keys)."""

    value: str = Field(..., min_length=1)
    display_name: str | None = Field(default=None, max_length=240)
    api_base: str | None = Field(default=None, max_length=2048)

    @field_validator("display_name", "api_base", mode="before")
    @classmethod
    def strip_blank_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class IntegrationSecretCreatedOut(BaseModel):
    integration_secret_id: int
    integration_key: str
    created_at: datetime
    updated_at: datetime


class AiCredentialCatalogEntryOut(BaseModel):
    integration_secret_id: int | None = None
    integration_key: str
    credential_kind: Literal["preset", "custom"]
    provider: str | None = None
    configured: bool
    display_name: str | None = None
    has_api_base: bool = False
    assigned_model_config_id: str | None = None
    assigned_model_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AiProviderIntegrationCatalogEntryOut(BaseModel):
    """Backward-compatible preset-only shape (subset of the unified catalog)."""

    provider: str
    integration_key: str
    configured: bool
    display_name: str | None = None
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


def _assigned_model_for_integration_secret(
    session: Session, integration_secret_id: int
) -> BackfieldAiModelConfig | None:
    return session.exec(
        select(BackfieldAiModelConfig).where(
            BackfieldAiModelConfig.integration_secret_id == integration_secret_id,
        )
    ).first()


def assert_integration_secret_assignable_for_catalog_model(
    session: Session,
    organization_id: int,
    integration_secret_id: int,
    *,
    exclude_model_config_id: str | None,
) -> BackfieldOrganizationIntegrationSecret:
    row = session.get(BackfieldOrganizationIntegrationSecret, integration_secret_id)
    if row is None or int(row.organization_id) != organization_id:
        raise HTTPException(status_code=404, detail="Saved credential not found")
    if not is_custom_ai_credential_integration_key(str(row.integration_key)):
        raise HTTPException(
            status_code=400,
            detail="Catalog models must use a credential you added for your organization.",
        )
    stmt = select(BackfieldAiModelConfig).where(
        BackfieldAiModelConfig.integration_secret_id == integration_secret_id,
    )
    if exclude_model_config_id:
        stmt = stmt.where(BackfieldAiModelConfig.id != exclude_model_config_id)
    conflict = session.exec(stmt).first()
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail="That credential is already linked to another model.",
        )
    return row


def list_ai_credentials_catalog_entries(
    session: Session, organization_id: int
) -> list[AiCredentialCatalogEntryOut]:
    """User-created vendor credentials only (preset vendor slots are not listed here)."""

    out: list[AiCredentialCatalogEntryOut] = []

    custom_rows = session.exec(
        select(BackfieldOrganizationIntegrationSecret)
        .where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            col(BackfieldOrganizationIntegrationSecret.integration_key).startswith(
                INTEGRATION_KEY_AI_CREDENTIAL_PREFIX,
            ),
        )
        .order_by(col(BackfieldOrganizationIntegrationSecret.created_at))
    ).all()
    for row in custom_rows:
        rid = row.id
        sid = int(rid) if rid is not None else None
        assign = _assigned_model_for_integration_secret(session, sid) if sid is not None else None
        dn = None
        if row.credential_display_name:
            raw_dn = str(row.credential_display_name).strip()
            dn = raw_dn if raw_dn else None
        has_ab = bool((row.api_base or "").strip())
        out.append(
            AiCredentialCatalogEntryOut(
                integration_secret_id=sid,
                integration_key=str(row.integration_key),
                credential_kind="custom",
                provider=None,
                configured=True,
                display_name=dn,
                has_api_base=has_ab,
                assigned_model_config_id=str(assign.id) if assign else None,
                assigned_model_name=str(assign.name) if assign else None,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )

    return out


def list_ai_provider_catalog_entries(
    session: Session, organization_id: int
) -> list[AiProviderIntegrationCatalogEntryOut]:
    """Preset vendor slots only (legacy endpoint); not merged into ``…/catalog``."""
    by_preset_key = integration_keys_loaded(session, organization_id)
    out: list[AiProviderIntegrationCatalogEntryOut] = []
    for key in sorted(ORG_AI_PROVIDER_INTEGRATION_KEYS):
        slug = AI_PROVIDER_SLUG_BY_INTEGRATION_KEY[key]
        row = by_preset_key.get(key)
        dn = None
        if row is not None and row.credential_display_name:
            raw_dn = str(row.credential_display_name).strip()
            dn = raw_dn if raw_dn else None
        out.append(
            AiProviderIntegrationCatalogEntryOut(
                provider=slug,
                integration_key=key,
                configured=row is not None,
                display_name=dn,
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
            integration_secret_id=int(r.id) if r.id is not None else None,
            integration_key=r.integration_key,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def create_org_integration_credential(
    session: Session,
    organization_id: int,
    body: IntegrationSecretCreateBody,
) -> IntegrationSecretCreatedOut:
    """Insert ``ai.credential.<uuid>`` row (POST — no preset slot)."""
    assert_encryption_usable()
    try:
        enc = encrypt_secret(body.value)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from uuid import uuid4

    ik = f"{INTEGRATION_KEY_AI_CREDENTIAL_PREFIX}{uuid4()}"
    now = datetime.now(UTC)
    row = BackfieldOrganizationIntegrationSecret(
        organization_id=organization_id,
        integration_key=ik,
        credential_display_name=body.display_name,
        api_base=body.api_base,
        value_encrypted=enc,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    rid = row.id
    if rid is None:
        raise HTTPException(status_code=500, detail="Credential insert failed")
    return IntegrationSecretCreatedOut(
        integration_secret_id=int(rid),
        integration_key=str(row.integration_key),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def upsert_org_integration_secret(
    session: Session,
    organization_id: int,
    integration_key: str,
    plain_value: str,
    *,
    display_name: str | None = None,
    api_base: str | None = None,
) -> IntegrationSecretOut:
    key = integration_key.strip()
    if is_built_in_ai_provider_integration_key(key):
        pass
    elif is_custom_ai_credential_integration_key(key):
        existing_chk = session.exec(
            select(BackfieldOrganizationIntegrationSecret).where(
                BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
                BackfieldOrganizationIntegrationSecret.integration_key == key,
            )
        ).first()
        if existing_chk is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown credential key — use Add credential to create a new one.",
            )
    else:
        raise HTTPException(status_code=400, detail="Unsupported integration_key")

    assert_encryption_usable()
    try:
        enc = encrypt_secret(plain_value)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    now = datetime.now(UTC)
    existing = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            BackfieldOrganizationIntegrationSecret.integration_key == key,
        )
    ).first()
    if existing:
        existing.value_encrypted = enc
        existing.credential_display_name = display_name
        if api_base is not None:
            existing.api_base = api_base
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        rid = existing.id
        return IntegrationSecretOut(
            integration_secret_id=int(rid) if rid is not None else None,
            integration_key=existing.integration_key,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    if not is_built_in_ai_provider_integration_key(key):
        raise HTTPException(status_code=404, detail="Unknown credential key")

    row = BackfieldOrganizationIntegrationSecret(
        organization_id=organization_id,
        integration_key=key,
        credential_display_name=display_name,
        api_base=api_base,
        value_encrypted=enc,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    rid = row.id
    return IntegrationSecretOut(
        integration_secret_id=int(rid) if rid is not None else None,
        integration_key=row.integration_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def patch_org_integration_secret(
    session: Session,
    organization_id: int,
    integration_key: str,
    body: IntegrationSecretPatchBody,
) -> IntegrationSecretOut:
    key = integration_key.strip()
    row = session.exec(
        select(BackfieldOrganizationIntegrationSecret).where(
            BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
            BackfieldOrganizationIntegrationSecret.integration_key == key,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Secret not found")

    data = body.model_dump(exclude_unset=True)
    now = datetime.now(UTC)
    if "value" in data and data["value"] is not None:
        assert_encryption_usable()
        try:
            row.value_encrypted = encrypt_secret(str(data["value"]))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
    if "display_name" in data:
        row.credential_display_name = data["display_name"]
    if "api_base" in data:
        row.api_base = data["api_base"]
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    rid = row.id
    return IntegrationSecretOut(
        integration_secret_id=int(rid) if rid is not None else None,
        integration_key=row.integration_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def delete_org_integration_secret(
    session: Session, organization_id: int, integration_key: str
) -> None:
    key = integration_key.strip()
    if is_built_in_ai_provider_integration_key(key):
        row = session.exec(
            select(BackfieldOrganizationIntegrationSecret).where(
                BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
                BackfieldOrganizationIntegrationSecret.integration_key == key,
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Secret not found")
        session.delete(row)
        session.commit()
        return

    if is_custom_ai_credential_integration_key(key):
        row = session.exec(
            select(BackfieldOrganizationIntegrationSecret).where(
                BackfieldOrganizationIntegrationSecret.organization_id == organization_id,
                BackfieldOrganizationIntegrationSecret.integration_key == key,
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Secret not found")
        rid = row.id
        if rid is not None:
            assign = _assigned_model_for_integration_secret(session, int(rid))
            if assign is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Unlink or delete the catalog model that uses this credential first.",
                )
        session.delete(row)
        session.commit()
        return

    raise HTTPException(status_code=400, detail="Unsupported integration_key")
