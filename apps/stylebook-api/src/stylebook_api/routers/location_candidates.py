"""Location candidate queue: substrate rows not yet linked to a Stylebook canonical."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from backfield_stylebook.locations import refresh_aliases_for_linked_location
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import exists
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1", tags=["location-candidates"])


def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    row = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def _require_stylebook_id(session: Session, project: BackfieldProject) -> int:
    try:
        return resolve_stylebook_id_for_project_id(session, int(project.id))
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class PaginatedClustersResponse(BaseModel):
    clusters: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_prev: bool


class PaginatedCandidatesResponse(BaseModel):
    candidates: list[dict[str, Any]]
    total: int
    has_next: bool
    has_prev: bool


def _open_candidate_filters(
    project_id: int,
    *,
    needs_review: bool | None,
) -> list[Any]:
    filters: list[Any] = [
        SubstrateLocation.project_id == project_id,
        col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
        SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
    ]
    if needs_review is True:
        filters.append(
            exists().where(
                SubstrateLocationMention.location_id == SubstrateLocation.id,
                SubstrateLocationMention.deleted == False,  # noqa: E712
                SubstrateLocationMention.needs_review == True,  # noqa: E712
            )
        )
    return filters


def _candidate_dict(loc: SubstrateLocation) -> dict[str, Any]:
    return {
        "id": int(loc.id),  # type: ignore[arg-type]
        "project_id": int(loc.project_id),
        "suggested_name": str(loc.name),
        "suggested_type": loc.location_type or "",
        "suggested_formatted_address": loc.formatted_address,
        "status": "open",
    }


def _list_open_candidates(
    session: Session,
    *,
    project_id: int,
    limit: int,
    offset: int,
    needs_review: bool | None,
) -> PaginatedCandidatesResponse:
    filters = _open_candidate_filters(project_id, needs_review=needs_review)
    count_stmt = select(func.count()).select_from(SubstrateLocation).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstrateLocation)
        .where(*filters)
        .order_by(col(SubstrateLocation.updated_at).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(session.exec(stmt).all())
    candidates = [_candidate_dict(r) for r in rows]
    return PaginatedCandidatesResponse(
        candidates=candidates,
        total=total,
        has_next=offset + len(candidates) < total,
        has_prev=offset > 0,
    )


@router.get("/candidates", response_model=PaginatedCandidatesResponse)
def candidates_list(
    project_slug: str = Query(...),
    status: str = Query("open"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    needs_review: bool | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    if status not in ("open", "all"):
        raise HTTPException(status_code=400, detail="Only status=open or all is supported")
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj)
    if status == "all":
        raise HTTPException(status_code=400, detail="status=all is not implemented for this queue")
    return _list_open_candidates(
        session,
        project_id=int(proj.id),
        limit=limit,
        offset=offset,
        needs_review=needs_review,
    )


@router.get("/candidates/ungrouped", response_model=PaginatedCandidatesResponse)
def candidates_ungrouped(
    project_slug: str = Query(...),
    status: str = Query("open"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    needs_review: bool | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    if status not in ("open", "all"):
        raise HTTPException(status_code=400, detail="Only status=open or all is supported")
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj)
    if status == "all":
        raise HTTPException(status_code=400, detail="status=all is not implemented for this queue")
    return _list_open_candidates(
        session,
        project_id=int(proj.id),
        limit=limit,
        offset=offset,
        needs_review=needs_review,
    )


@router.get("/candidates/clusters", response_model=PaginatedClustersResponse)
def candidates_clusters(
    project_slug: str = Query(...),
    status: str = Query("open"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedClustersResponse:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj)
    return PaginatedClustersResponse(
        clusters=[],
        total=0,
        limit=limit,
        offset=offset,
        has_next=False,
        has_prev=False,
    )


@router.get("/candidates/types", response_model=dict[str, list[str]])
def candidates_types(
    project_slug: str = Query(...),
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj)
    filters = _open_candidate_filters(int(proj.id), needs_review=None)
    stmt = (
        select(SubstrateLocation.location_type)
        .where(*filters)
        .where(col(SubstrateLocation.location_type).is_not(None))
        .distinct()
    )
    raw = session.exec(stmt).all()
    types = sorted({str(t) for t in raw if t})
    return {"types": types}


class AcceptCandidateBody(BaseModel):
    create_new: bool = False
    stylebook_location_id: int | None = None
    name: str | None = None
    geometry_json: dict[str, Any] | None = None


@router.post("/candidates/{substrate_location_id}/accept")
def accept_candidate(
    substrate_location_id: int,
    project_slug: str = Query(...),
    body: AcceptCandidateBody = Body(default_factory=AcceptCandidateBody),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)

    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    if loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Location already linked to a canonical")
    if loc.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=400,
            detail="Location is not in the canonical review queue (status must be pending)",
        )

    if body.create_new:
        label = (body.name or loc.name or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="name is required when create_new is true")
        gj = body.geometry_json
        canon = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label=label,
            primary_substrate_location_id=None,
            status="active",
            geometry_json=dict(gj) if isinstance(gj, dict) else gj,
            geometry_type=(gj or {}).get("type") if isinstance(gj, dict) else None,
        )
        session.add(canon)
        session.flush()
        loc.stylebook_location_canonical_id = int(canon.id)  # type: ignore[arg-type]
    else:
        if body.stylebook_location_id is None:
            raise HTTPException(
                status_code=400,
                detail="stylebook_location_id is required when create_new is false",
            )
        canon = session.get(StylebookLocationCanonical, body.stylebook_location_id)
        if canon is None:
            raise HTTPException(status_code=404, detail="Canonical location not found")
        if int(canon.stylebook_id) != int(stylebook_id):
            raise HTTPException(
                status_code=400,
                detail="Canonical is not in this project's Stylebook",
            )
        loc.stylebook_location_canonical_id = int(canon.id)  # type: ignore[arg-type]

    refresh_aliases_for_linked_location(
        session,
        stylebook_id=stylebook_id,
        location=loc,
        provenance="stylebook_ui_accept",
    )
    loc.canonical_link_status = CANONICAL_LINK_LINKED
    if body.create_new:
        loc.canonical_review_reasons_json = [
            {
                "code": "linked_manual_accept_create_new",
                "canonical_id": int(canon.id),  # type: ignore[arg-type]
            }
        ]
    else:
        loc.canonical_review_reasons_json = [
            {
                "code": "linked_manual_accept_existing",
                "canonical_id": int(canon.id),  # type: ignore[arg-type]
            }
        ]
    session.add(loc)
    session.commit()
    return {"message": "linked"}
