"""Per-project API credentials (user keys and service principals)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from backfield_db import BackfieldApiCredential
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from core_api.authz import require_org_admin, require_project_access
from core_api.deps import get_auth, get_session

router = APIRouter(prefix="/projects", tags=["credentials"])


def _hash_raw_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CreateCredentialBody(BaseModel):
    credential_type: str  # "user" | "service"
    label: str | None = None


class CredentialOut(BaseModel):
    id: int
    credential_type: str
    key_prefix: str
    label: str | None
    created_at: datetime
    revoked_at: datetime | None


class CreateCredentialResponse(CredentialOut):
    raw_key: str


@router.post("/{project_id}/api-keys", response_model=CreateCredentialResponse)
def create_api_key(
    project_id: int,
    body: CreateCredentialBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    if body.credential_type not in ("user", "service"):
        raise HTTPException(status_code=400, detail="credential_type must be user or service")

    proj = require_project_access(session, auth, project_id)

    if body.credential_type == "service":
        require_org_admin(session, auth, int(proj.organization_id))
        uid = None
    else:
        if auth["type"] != "session":
            raise HTTPException(status_code=400, detail="User keys require a browser session")
        uid = int(auth["user"].id)  # type: ignore[union-attr]

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
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return CreateCredentialResponse(
        id=int(row.id),
        credential_type=row.credential_type,
        key_prefix=row.key_prefix,
        label=row.label,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        raw_key=raw,
    )


@router.get("/{project_id}/api-keys", response_model=list[CredentialOut])
def list_api_keys(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    rows = session.exec(
        select(BackfieldApiCredential).where(BackfieldApiCredential.project_id == project_id)
    ).all()
    active = [r for r in rows if r.revoked_at is None]
    return [
        CredentialOut(
            id=int(r.id),
            credential_type=r.credential_type,
            key_prefix=r.key_prefix,
            label=r.label,
            created_at=r.created_at,
            revoked_at=r.revoked_at,
        )
        for r in active
    ]


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
    row.revoked_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return None
