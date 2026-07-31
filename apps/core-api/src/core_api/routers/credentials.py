"""Per-project API credentials (user keys and service principals)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Literal

from backfield_auth.gate import (
    ALL_SCOPES,
    SCOPE_READ,
    SCOPE_RUNS_TRIGGER,
    parse_scopes,
)
from backfield_db import BackfieldApiCredential
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select

from core_api.authz import require_org_admin, require_project_access
from core_api.deps import get_auth, get_session

router = APIRouter(prefix="/projects", tags=["credentials"])
CredentialType = Literal["user", "service"]
CredentialScope = Literal["read", "runs:trigger"]


def _hash_raw_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_requested_scopes(
    requested: list[str] | None,
    *,
    credential_type: CredentialType,
) -> list[CredentialScope]:
    tokens = [t.strip() for t in (requested or []) if t and t.strip()]
    if not tokens:
        return [SCOPE_READ]
    unknown = sorted(set(tokens) - set(ALL_SCOPES))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scope(s): {', '.join(unknown)}",
        )
    if SCOPE_RUNS_TRIGGER in tokens and credential_type != "service":
        raise HTTPException(
            status_code=400,
            detail="runs:trigger requires a service key",
        )
    normalized: list[CredentialScope] = [SCOPE_READ]
    for scope in ALL_SCOPES:
        if scope != SCOPE_READ and scope in tokens:
            normalized.append(scope)
    return normalized


def _credential_out(row: BackfieldApiCredential) -> CredentialOut:
    return CredentialOut(
        id=int(row.id),
        credential_type=row.credential_type,
        key_prefix=row.key_prefix,
        label=row.label,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        user_id=int(row.user_id) if row.user_id is not None else None,
        scopes=parse_scopes(row.scopes),
    )


class CreateCredentialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_type: CredentialType
    label: str | None = Field(default=None, max_length=200)
    scopes: list[CredentialScope] | None = Field(default=None, max_length=len(ALL_SCOPES))

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CredentialOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    credential_type: CredentialType
    key_prefix: str
    label: str | None
    created_at: datetime
    revoked_at: datetime | None
    user_id: int | None = None
    scopes: list[CredentialScope]


class CreateCredentialResponse(CredentialOut):
    raw_key: str


@router.post("/{project_id}/api-keys", response_model=CreateCredentialResponse)
def create_api_key(
    project_id: int,
    body: CreateCredentialBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    proj = require_project_access(session, auth, project_id)

    if body.credential_type == "service":
        require_org_admin(session, auth, int(proj.organization_id))
        uid = None
    else:
        if auth["type"] != "session":
            raise HTTPException(status_code=400, detail="User keys require a browser session")
        uid = int(auth["user"].id)  # type: ignore[union-attr]

    normalized_scopes = _normalize_requested_scopes(
        body.scopes,
        credential_type=body.credential_type,
    )

    raw = "bfk_" + secrets.token_urlsafe(32)
    prefix = raw[:22]
    digest = _hash_raw_key(raw)

    row = BackfieldApiCredential(
        project_id=project_id,
        user_id=uid,
        credential_type=body.credential_type,
        key_prefix=prefix,
        key_hash=digest,
        label=body.label,
        scopes=" ".join(normalized_scopes),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return CreateCredentialResponse(
        **_credential_out(row).model_dump(),
        raw_key=raw,
    )


@router.get("/{project_id}/api-keys", response_model=list[CredentialOut])
def list_api_keys(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    statement = select(BackfieldApiCredential).where(
        BackfieldApiCredential.project_id == project_id
    )
    if auth["type"] == "session" and auth.get("org_role") != "org_admin":
        statement = statement.where(
            BackfieldApiCredential.credential_type == "user",
            BackfieldApiCredential.user_id == int(auth["user"].id),
        )
    rows = session.exec(
        statement.order_by(BackfieldApiCredential.created_at.desc())
    ).all()
    return [_credential_out(row) for row in rows]


@router.delete("/{project_id}/api-keys/{credential_id}", status_code=204)
def revoke_api_key(
    project_id: int,
    credential_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    proj = require_project_access(session, auth, project_id)
    row = session.get(BackfieldApiCredential, credential_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="Credential not found")
    if auth["type"] == "session":
        uid = int(auth["user"].id)  # type: ignore[union-attr]
        org_id = int(proj.organization_id)
        if row.credential_type == "service":
            require_org_admin(session, auth, org_id)
        elif row.user_id != uid:
            require_org_admin(session, auth, org_id)
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        session.add(row)
        session.commit()
    return None
