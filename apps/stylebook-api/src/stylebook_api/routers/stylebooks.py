"""Org-scoped Stylebook catalog (library CRUD and delete flow)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backfield_auth.gate import require_org_admin
from backfield_db import BackfieldUser, Stylebook, StylebookMembership
from backfield_entities.graph_stylebook_refs import count_stylebook_usage_in_graphs
from backfield_entities.stylebook_library import (
    StylebookLibraryError,
    resolve_stylebook_by_slug,
    set_org_default_stylebook,
)
from backfield_entities.stylebook_library import (
    create_stylebook as domain_create_stylebook,
)
from backfield_entities.stylebook_library import (
    delete_stylebook as domain_delete_stylebook,
)
from backfield_entities.stylebook_library import (
    rename_stylebook as domain_rename_stylebook,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1/organizations", tags=["stylebooks"])


def _require_org_scope(auth: dict[str, Any], org_id: int) -> None:
    if auth["type"] == "service":
        return
    if int(auth["organization_id"]) != org_id:
        raise HTTPException(status_code=403, detail="Wrong organization")


class StylebookCreateBody(BaseModel):
    name: str = Field(min_length=1)
    is_default: bool = False


class StylebookRenameBody(BaseModel):
    name: str = Field(min_length=1)


class StylebookDeleteBody(BaseModel):
    confirm_name: str = Field(min_length=1)
    replacement_default_id: int | None = None


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


class StylebookDeletePreviewOut(BaseModel):
    stylebook_id: int
    name: str
    is_default: bool
    is_only_stylebook_in_org: bool
    graphs_referencing: int
    nodes_referencing: int


class StylebookMemberOut(BaseModel):
    user_id: int
    email: str
    role: str
    created_at: datetime


class StylebookMemberCreateBody(BaseModel):
    user_id: int | None = None
    email: str | None = None
    role: str = "editor"


def _http_from_library(err: StylebookLibraryError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/{org_id}/stylebooks", response_model=list[StylebookOut])
def list_stylebooks(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[StylebookOut]:
    _require_org_scope(auth, org_id)
    rows = session.exec(
        select(Stylebook).where(Stylebook.organization_id == org_id).order_by(col(Stylebook.name))
    ).all()
    return [StylebookOut.from_row(r) for r in rows]


@router.get("/{org_id}/stylebooks/by-slug/{slug}", response_model=StylebookOut)
def get_stylebook_by_slug(
    org_id: int,
    slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookOut:
    _require_org_scope(auth, org_id)
    row = resolve_stylebook_by_slug(session, organization_id=org_id, slug=slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    return StylebookOut.from_row(row)


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
    try:
        row = domain_create_stylebook(
            session,
            organization_id=org_id,
            name=label,
            is_default=body.is_default,
        )
        session.commit()
        session.refresh(row)
    except StylebookLibraryError as e:
        session.rollback()
        raise _http_from_library(e) from e
    return StylebookOut.from_row(row)


@router.patch("/{org_id}/stylebooks/{stylebook_id}", response_model=StylebookOut)
def rename_stylebook(
    org_id: int,
    stylebook_id: int,
    body: StylebookRenameBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookOut:
    require_org_admin(session, auth, org_id)
    row = session.get(Stylebook, stylebook_id)
    if row is None or int(row.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    label = body.name.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Name is required")
    try:
        row = domain_rename_stylebook(session, stylebook_id=stylebook_id, new_name=label)
        session.commit()
        session.refresh(row)
    except StylebookLibraryError as e:
        session.rollback()
        raise _http_from_library(e) from e
    return StylebookOut.from_row(row)


@router.post("/{org_id}/stylebooks/{stylebook_id}/set-default", response_model=StylebookOut)
def set_default_stylebook(
    org_id: int,
    stylebook_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookOut:
    require_org_admin(session, auth, org_id)
    try:
        row = set_org_default_stylebook(
            session,
            organization_id=org_id,
            stylebook_id=stylebook_id,
        )
        session.commit()
        session.refresh(row)
    except StylebookLibraryError as e:
        session.rollback()
        raise _http_from_library(e) from e
    return StylebookOut.from_row(row)


@router.get(
    "/{org_id}/stylebooks/{stylebook_id}/delete-preview",
    response_model=StylebookDeletePreviewOut,
)
def delete_stylebook_preview(
    org_id: int,
    stylebook_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookDeletePreviewOut:
    require_org_admin(session, auth, org_id)
    row = session.get(Stylebook, stylebook_id)
    if row is None or int(row.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    all_sb = session.exec(
        select(Stylebook.id).where(Stylebook.organization_id == org_id)
    ).all()
    only_one = len(all_sb) <= 1

    gc, nc = count_stylebook_usage_in_graphs(
        session,
        organization_id=org_id,
        stylebook_id=stylebook_id,
    )
    return StylebookDeletePreviewOut(
        stylebook_id=stylebook_id,
        name=str(row.name),
        is_default=bool(row.is_default),
        is_only_stylebook_in_org=only_one,
        graphs_referencing=gc,
        nodes_referencing=nc,
    )


@router.post("/{org_id}/stylebooks/{stylebook_id}/delete", status_code=204)
def delete_stylebook_endpoint(
    org_id: int,
    stylebook_id: int,
    body: StylebookDeleteBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    require_org_admin(session, auth, org_id)
    row = session.get(Stylebook, stylebook_id)
    if row is None or int(row.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    typed = body.confirm_name.strip()
    if typed != str(row.name).strip():
        raise HTTPException(
            status_code=400,
            detail="Confirmation name does not match this stylebook.",
        )

    replacement = body.replacement_default_id
    if row.is_default:
        all_sb = session.exec(
            select(Stylebook.id).where(Stylebook.organization_id == org_id)
        ).all()
        if len(all_sb) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last stylebook for an organization.",
            )
        if replacement is None:
            raise HTTPException(
                status_code=400,
                detail="Choose another stylebook to be the default before deleting this one.",
            )

    try:
        domain_delete_stylebook(
            session,
            stylebook_id,
            replacement_default_id=replacement,
        )
        session.commit()
    except StylebookLibraryError as e:
        session.rollback()
        raise _http_from_library(e) from e


@router.get("/{org_id}/stylebooks/{stylebook_id}/members", response_model=list[StylebookMemberOut])
def list_stylebook_members(
    org_id: int,
    stylebook_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[StylebookMemberOut]:
    require_org_admin(session, auth, org_id)
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    rows = session.exec(
        select(StylebookMembership, BackfieldUser)
        .join(BackfieldUser, BackfieldUser.id == StylebookMembership.user_id)
        .where(StylebookMembership.stylebook_id == stylebook_id)
        .order_by(col(BackfieldUser.email))
    ).all()
    return [
        StylebookMemberOut(
            user_id=int(m.user_id),
            email=str(u.email),
            role=str(m.role),
            created_at=m.created_at,
        )
        for m, u in rows
    ]


@router.post("/{org_id}/stylebooks/{stylebook_id}/members", response_model=list[StylebookMemberOut])
def add_stylebook_member(
    org_id: int,
    stylebook_id: int,
    body: StylebookMemberCreateBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[StylebookMemberOut]:
    require_org_admin(session, auth, org_id)
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    role = (body.role or "").strip().lower()
    if role != "editor":
        raise HTTPException(status_code=400, detail="role must be editor")

    uid: int | None = int(body.user_id) if body.user_id is not None else None
    email = (body.email or "").strip().lower() or None
    if uid is None and email is None:
        raise HTTPException(status_code=400, detail="Provide user_id or email")

    user: BackfieldUser | None
    if uid is not None:
        user = session.get(BackfieldUser, uid)
    else:
        user = session.exec(select(BackfieldUser).where(col(BackfieldUser.email) == email)).first()
    if user is None or user.id is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = session.exec(
        select(StylebookMembership).where(
            StylebookMembership.stylebook_id == stylebook_id,
            StylebookMembership.user_id == int(user.id),
        )
    ).first()
    if existing is None:
        session.add(
            StylebookMembership(
                stylebook_id=stylebook_id,
                user_id=int(user.id),
                role=role,
            )
        )
        session.commit()

    return list_stylebook_members(org_id, stylebook_id, session, auth)


@router.delete("/{org_id}/stylebooks/{stylebook_id}/members/{user_id}", status_code=204)
def remove_stylebook_member(
    org_id: int,
    stylebook_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    require_org_admin(session, auth, org_id)
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    row = session.exec(
        select(StylebookMembership).where(
            StylebookMembership.stylebook_id == stylebook_id,
            StylebookMembership.user_id == int(user_id),
        )
    ).first()
    if row is None:
        return
    session.delete(row)
    session.commit()
