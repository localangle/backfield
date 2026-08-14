"""CRUD for typed metadata attributes on ``stylebook_person_canonical``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from backfield_db import BackfieldProject, StylebookPersonCanonical, StylebookPersonMeta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.meta_utils import (
    apply_typed_values_to_row,
    normalize_meta_type_or_400,
    parse_meta_write,
    serialize_meta_row,
)
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1", tags=["person-meta"])

ValueTypeLiteral = Literal["text", "number", "boolean"]


class UpdateMetaRequest(BaseModel):
    meta_type: str | None = Field(
        default=None,
        description="When set, replaces the meta type slug",
    )
    value_type: ValueTypeLiteral
    value: str | int | float | bool


class CreateMetaRequest(BaseModel):
    meta_type: str = Field(..., min_length=1)
    value_type: ValueTypeLiteral
    value: str | int | float | bool


def _canonical_for_stylebook_or_404(
    session: Session,
    *,
    stylebook_slug: str,
    canonical_id: UUID,
    auth: dict[str, Any],
) -> StylebookPersonCanonical:
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    return canon


def _stylebook_storage_project_id(session: Session, *, organization_id: int) -> int:
    row = session.exec(
        select(BackfieldProject.id)
        .where(BackfieldProject.organization_id == organization_id)
        .order_by(BackfieldProject.id.asc())
    ).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="This stylebook needs at least one project before metadata can be edited.",
        )
    return int(row)


@router.get("/stylebooks/{stylebook_slug}/canonical-people/{canonical_id}/meta")
def get_stylebook_person_meta(
    stylebook_slug: str,
    canonical_id: UUID,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    _canonical_for_stylebook_or_404(
        session, stylebook_slug=stylebook_slug, canonical_id=canonical_id, auth=auth
    )
    cid = str(canonical_id)
    rows = session.exec(
        select(StylebookPersonMeta)
        .where(StylebookPersonMeta.stylebook_person_canonical_id == cid)
        .order_by(StylebookPersonMeta.meta_type, StylebookPersonMeta.id)
    ).all()
    meta_out = [serialize_meta_row(m) for m in rows]
    return {
        "person_id": cid,
        "meta": meta_out,
        "count": len(meta_out),
    }


@router.post("/stylebooks/{stylebook_slug}/canonical-people/{canonical_id}/meta")
def upsert_stylebook_person_meta(
    stylebook_slug: str,
    canonical_id: UUID,
    payload: CreateMetaRequest,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    _canonical_for_stylebook_or_404(
        session, stylebook_slug=stylebook_slug, canonical_id=canonical_id, auth=auth
    )
    cid = str(canonical_id)
    write = parse_meta_write(
        meta_type=payload.meta_type,
        value_type=payload.value_type,
        value=payload.value,
    )
    existing = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.stylebook_person_canonical_id == cid,
            StylebookPersonMeta.meta_type == write.meta_type,
        )
    ).first()
    if existing is not None:
        apply_typed_values_to_row(
            existing,
            meta_type=write.meta_type,
            value_type=write.value_type,
            value=write.value,
        )
        existing.edited = True
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return serialize_meta_row(existing)

    row = StylebookPersonMeta(
        project_id=_stylebook_storage_project_id(
            session, organization_id=int(sb.organization_id)
        ),
        stylebook_person_canonical_id=cid,
        added=True,
        created_at=datetime.now(UTC),
    )
    apply_typed_values_to_row(
        row,
        meta_type=write.meta_type,
        value_type=write.value_type,
        value=write.value,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_meta_row(row)


@router.patch("/stylebooks/{stylebook_slug}/canonical-people/{canonical_id}/meta/{meta_id}")
def update_stylebook_person_meta(
    stylebook_slug: str,
    canonical_id: UUID,
    meta_id: int,
    request: UpdateMetaRequest,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    _canonical_for_stylebook_or_404(
        session, stylebook_slug=stylebook_slug, canonical_id=canonical_id, auth=auth
    )
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.id == meta_id,
            StylebookPersonMeta.stylebook_person_canonical_id == cid,
        )
    ).first()
    if meta_row is None:
        raise HTTPException(status_code=404, detail="Meta record not found")

    meta_type = (
        normalize_meta_type_or_400(request.meta_type)
        if request.meta_type is not None
        else meta_row.meta_type
    )
    write = parse_meta_write(
        meta_type=meta_type,
        value_type=request.value_type,
        value=request.value,
    )
    if write.meta_type != meta_row.meta_type:
        clash = session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == cid,
                StylebookPersonMeta.meta_type == write.meta_type,
                StylebookPersonMeta.id != meta_id,
            )
        ).first()
        if clash is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Metadata key '{write.meta_type}' already exists on this record",
            )
    apply_typed_values_to_row(
        meta_row,
        meta_type=write.meta_type,
        value_type=write.value_type,
        value=write.value,
    )
    meta_row.edited = True
    session.add(meta_row)
    session.commit()
    session.refresh(meta_row)
    return serialize_meta_row(meta_row)


@router.delete("/stylebooks/{stylebook_slug}/canonical-people/{canonical_id}/meta/{meta_id}")
def delete_stylebook_person_meta(
    stylebook_slug: str,
    canonical_id: UUID,
    meta_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    _canonical_for_stylebook_or_404(
        session, stylebook_slug=stylebook_slug, canonical_id=canonical_id, auth=auth
    )
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.id == meta_id,
            StylebookPersonMeta.stylebook_person_canonical_id == cid,
        )
    ).first()
    if meta_row is None:
        raise HTTPException(status_code=404, detail="Meta record not found")
    session.delete(meta_row)
    session.commit()
    return {"message": "Meta record deleted successfully"}
