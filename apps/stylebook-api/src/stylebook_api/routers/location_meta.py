"""CRUD for JSON metadata rows on ``stylebook_location_canonical``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject, StylebookLocationCanonical, StylebookLocationMeta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.meta_utils import parse_meta_json, validate_meta_json
from stylebook_api.routers.locations import _project_by_slug, _require_stylebook_id

router = APIRouter(prefix="/v1", tags=["location-meta"])


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
) -> StylebookLocationCanonical:
    stylebook_id = _require_stylebook_id(session, project)
    canon = session.get(StylebookLocationCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    return canon


@router.get("/canonical-locations/{canonical_id}/meta")
def get_location_meta(
    canonical_id: UUID,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id)
    cid = str(canonical_id)
    rows = session.exec(
        select(StylebookLocationMeta)
        .where(StylebookLocationMeta.stylebook_location_canonical_id == cid)
        .order_by(StylebookLocationMeta.meta_type, StylebookLocationMeta.id)
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
        "location_id": cid,
        "meta": meta_out,
        "count": len(meta_out),
    }


@router.post("/canonical-locations/{canonical_id}/meta")
def create_location_meta(
    canonical_id: UUID,
    payload: CreateMetaRequest,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id)
    cid = str(canonical_id)
    validate_meta_json(payload.data)
    row = StylebookLocationMeta(
        project_id=int(proj.id),
        stylebook_location_canonical_id=cid,
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


@router.patch("/canonical-locations/{canonical_id}/meta/{meta_id}")
def update_location_meta(
    canonical_id: UUID,
    meta_id: int,
    request: UpdateMetaRequest,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id)
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookLocationMeta).where(
            StylebookLocationMeta.id == meta_id,
            StylebookLocationMeta.stylebook_location_canonical_id == cid,
            StylebookLocationMeta.project_id == int(proj.id),
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


@router.delete("/canonical-locations/{canonical_id}/meta/{meta_id}")
def delete_location_meta(
    canonical_id: UUID,
    meta_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _canonical_for_project_or_404(session, proj, canonical_id)
    cid = str(canonical_id)
    meta_row = session.exec(
        select(StylebookLocationMeta).where(
            StylebookLocationMeta.id == meta_id,
            StylebookLocationMeta.stylebook_location_canonical_id == cid,
            StylebookLocationMeta.project_id == int(proj.id),
        )
    ).first()
    if meta_row is None:
        raise HTTPException(status_code=404, detail="Meta record not found")
    session.delete(meta_row)
    session.commit()
    return {"message": "Meta record deleted successfully"}
