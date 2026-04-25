"""Org-scoped Stylebook catalog."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backfield_auth.gate import require_org_admin
from backfield_db import Stylebook
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1/organizations", tags=["stylebooks"])


def _require_org_scope(auth: dict[str, Any], org_id: int) -> None:
    if auth["type"] == "service":
        return
    if int(auth["organization_id"]) != org_id:
        raise HTTPException(status_code=403, detail="Wrong organization")


def _slugify(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "stylebook"


class StylebookCreateBody(BaseModel):
    name: str
    slug: str | None = None


class StylebookOut(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Stylebook) -> StylebookOut:
        return cls(
            id=int(row.id),  # type: ignore[arg-type]
            organization_id=int(row.organization_id),
            name=str(row.name),
            slug=str(row.slug),
            is_default=bool(row.is_default),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@router.get("/{org_id}/stylebooks", response_model=list[StylebookOut])
def list_stylebooks(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[StylebookOut]:
    _require_org_scope(auth, org_id)
    rows = session.exec(
        select(Stylebook).where(Stylebook.organization_id == org_id).order_by(col(Stylebook.slug))
    ).all()
    return [StylebookOut.from_row(r) for r in rows]


@router.post("/{org_id}/stylebooks", response_model=StylebookOut)
def create_stylebook(
    org_id: int,
    body: StylebookCreateBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookOut:
    require_org_admin(session, auth, org_id)
    label = body.name.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Name is required")
    base = _slugify(body.slug or label)
    slug = base
    n = 2
    while True:
        hit = session.exec(
            select(Stylebook.id).where(
                Stylebook.organization_id == org_id,
                Stylebook.slug == slug,
            )
        ).first()
        if hit is None:
            break
        slug = f"{base}-{n}"
        n += 1
    row = Stylebook(
        organization_id=org_id,
        slug=slug,
        name=label,
        is_default=False,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return StylebookOut.from_row(row)
