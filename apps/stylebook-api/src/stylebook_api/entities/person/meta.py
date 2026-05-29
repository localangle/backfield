"""CRUD for JSON metadata rows on ``stylebook_person_canonical``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject, StylebookPersonCanonical, StylebookPersonMeta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.meta_utils import parse_meta_json, validate_meta_json
from stylebook_api.helpers.project_scope import (
    project_by_slug as _project_by_slug,
)
from stylebook_api.helpers.project_scope import (
    require_stylebook_id as _require_stylebook_id,
)
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1", tags=["person-meta"])


class UpdateMetaRequest(BaseModel):
    meta_type: str | None = Field(
        default=None,
        description="When set, replaces the meta type (non-empty after strip)",
    )
    data: Any = Field(..., description="Meta payload (JSON object, array, or scalar)")


class CreateMetaRequest(BaseModel):
    meta_type: str = Field(..., min_length=1)
    data: Any = Field(..., description="Meta payload (JSON object, array, or scalar)")


def _canonical_for_project_or_404(
    session: Session,
    project: BackfieldProject,
    canonical_id: UUID,
    stylebook_slug: str | None = None,
) -> StylebookPersonCanonical:
    stylebook_id = _require_stylebook_id(session, project, stylebook_slug)
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    return canon


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


@router.get("/canonical-people/{canonical_id}/meta")
def get_person_meta(
    canonical_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id, stylebook_slug)
    cid = str(canonical_id)
    rows = session.exec(
        select(StylebookPersonMeta)
        .where(StylebookPersonMeta.stylebook_person_canonical_id == cid)
        .order_by(StylebookPersonMeta.meta_type, StylebookPersonMeta.id)
    ).all()
    meta_out: list[dict[str, Any]] = []
    for m in rows:
        meta_out.append(
            {
                "id": m.id,
                "meta_type": m.meta_type,
                "data": parse_meta_json(m.data_json),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {
        "person_id": cid,
        "meta": meta_out,
        "count": len(meta_out),
    }


@router.post("/canonical-people/{canonical_id}/meta")
def create_person_meta(
    canonical_id: UUID,
    payload: CreateMetaRequest,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id, stylebook_slug)
    cid = str(canonical_id)
    validate_meta_json(payload.data)
    row = StylebookPersonMeta(
        project_id=int(proj.id),
        stylebook_person_canonical_id=cid,
        meta_type=payload.meta_type.strip(),
        data_json=payload.data,
        added=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "id": row.id,
        "meta_type": row.meta_type,
        "data": parse_meta_json(row.data_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.patch("/canonical-people/{canonical_id}/meta/{meta_id}")
def update_person_meta(
    canonical_id: UUID,
    meta_id: int,
    request: UpdateMetaRequest,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id, stylebook_slug)
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.id == meta_id,
            StylebookPersonMeta.stylebook_person_canonical_id == cid,
            StylebookPersonMeta.project_id == int(proj.id),
        )
    ).first()
    if meta_row is None:
        raise HTTPException(status_code=404, detail="Meta record not found")
    validate_meta_json(request.data)
    if request.meta_type is not None:
        mt = request.meta_type.strip()
        if not mt:
            raise HTTPException(status_code=400, detail="meta_type cannot be empty")
        meta_row.meta_type = mt
    meta_row.data_json = request.data
    meta_row.edited = True
    session.add(meta_row)
    session.commit()
    session.refresh(meta_row)
    return {
        "id": meta_row.id,
        "meta_type": meta_row.meta_type,
        "data": parse_meta_json(meta_row.data_json),
        "created_at": meta_row.created_at.isoformat() if meta_row.created_at else None,
    }


@router.delete("/canonical-people/{canonical_id}/meta/{meta_id}")
def delete_person_meta(
    canonical_id: UUID,
    meta_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id, stylebook_slug)
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.id == meta_id,
            StylebookPersonMeta.stylebook_person_canonical_id == cid,
            StylebookPersonMeta.project_id == int(proj.id),
        )
    ).first()
    if meta_row is None:
        raise HTTPException(status_code=404, detail="Meta record not found")
    session.delete(meta_row)
    session.commit()
    return {"message": "Meta record deleted successfully"}


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
    meta_out: list[dict[str, Any]] = []
    for m in rows:
        meta_out.append(
            {
                "id": m.id,
                "meta_type": m.meta_type,
                "data": parse_meta_json(m.data_json),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {
        "person_id": cid,
        "meta": meta_out,
        "count": len(meta_out),
    }


@router.post("/stylebooks/{stylebook_slug}/canonical-people/{canonical_id}/meta")
def create_stylebook_person_meta(
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
    validate_meta_json(payload.data)
    row = StylebookPersonMeta(
        project_id=_stylebook_storage_project_id(
            session, organization_id=int(sb.organization_id)
        ),
        stylebook_person_canonical_id=cid,
        meta_type=payload.meta_type.strip(),
        data_json=payload.data,
        added=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "id": row.id,
        "meta_type": row.meta_type,
        "data": parse_meta_json(row.data_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


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
    validate_meta_json(request.data)
    if request.meta_type is not None:
        mt = request.meta_type.strip()
        if not mt:
            raise HTTPException(status_code=400, detail="meta_type cannot be empty")
        meta_row.meta_type = mt
    meta_row.data_json = request.data
    meta_row.edited = True
    session.add(meta_row)
    session.commit()
    session.refresh(meta_row)
    return {
        "id": meta_row.id,
        "meta_type": meta_row.meta_type,
        "data": parse_meta_json(meta_row.data_json),
        "created_at": meta_row.created_at.isoformat() if meta_row.created_at else None,
    }


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
