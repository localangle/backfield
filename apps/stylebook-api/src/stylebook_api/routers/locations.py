"""Project-scoped substrate locations (Stylebook UI compatibility, ``project_slug``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1", tags=["locations"])


def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    row = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _map_incoming_status(status: str | None) -> str | None:
    if status is None:
        return None
    s = status.strip().lower()
    if s == "draft":
        return "provisional"
    return s


def _status_expr(status: str | None) -> ColumnElement[bool] | None:
    if not status or status == "all":
        return None
    if status == "active":
        return col(SubstrateLocation.status).in_(["active", "provisional", "confirmed"])
    if status == "draft":
        return SubstrateLocation.status == "provisional"
    if status == "inactive":
        return SubstrateLocation.status == "inactive"
    return SubstrateLocation.status == status


class LocationResponse(BaseModel):
    id: int
    project_id: int
    name: str
    location_type: str
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None
    geometry_type: str | None = None
    status: str
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    mention_count: int = 0
    notes: str | None = None
    canonical_link_status: str | None = None
    canonical_review_reasons_json: list[Any] | dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: SubstrateLocation, mention_count: int = 0) -> LocationResponse:
        lt = row.location_type or ""
        return cls(
            id=int(row.id),  # type: ignore[arg-type]
            project_id=int(row.project_id),
            name=str(row.name),
            location_type=str(lt),
            formatted_address=row.formatted_address,
            geometry_json=row.geometry_json,
            geometry_type=row.geometry_type,
            status=str(row.status),
            created_by_user_id=None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            mention_count=mention_count,
            notes=None,
            canonical_link_status=str(row.canonical_link_status),
            canonical_review_reasons_json=row.canonical_review_reasons_json,
        )


class PaginatedLocationResponse(BaseModel):
    locations: list[LocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateLocationBody(BaseModel):
    name: str
    location_type: str
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None
    status: str | None = Field(
        default=None,
        description="draft | active (mapped to substrate statuses)",
    )


class PatchLocationBody(BaseModel):
    name: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    status: str | None = None
    notes: str | None = None


class PatchGeometryBody(BaseModel):
    geometry_json: dict[str, Any]


class PatchCanonicalGeometryBody(BaseModel):
    geometry_json: dict[str, Any]


def _require_stylebook_id(session: Session, project: BackfieldProject) -> int:
    try:
        return resolve_stylebook_id_for_project_id(session, int(project.id))
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _first_occurrence_mention_text_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, str]:
    """First non-suppressed occurrence text per location mention (stable quote for UI)."""
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateLocationMentionOccurrence)
        .where(
            col(SubstrateLocationMentionOccurrence.location_mention_id).in_(mention_ids),
            SubstrateLocationMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(SubstrateLocationMentionOccurrence.location_mention_id),
            col(SubstrateLocationMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstrateLocationMentionOccurrence.id),
        )
    ).all()
    out: dict[int, str] = {}
    for occ in rows:
        mid = int(occ.location_mention_id)
        if mid in out:
            continue
        txt = (occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


def _mention_counts(session: Session, location_ids: list[int]) -> dict[int, int]:
    if not location_ids:
        return {}
    rows = session.exec(
        select(SubstrateLocationMention.location_id, func.count(col(SubstrateLocationMention.id)))
        .where(
            col(SubstrateLocationMention.location_id).in_(location_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocationMention.location_id)
    ).all()
    out: dict[int, int] = {}
    for lid, cnt in rows:
        if lid is not None:
            out[int(lid)] = int(cnt)
    return out


@router.get("/locations", response_model=PaginatedLocationResponse)
def list_locations(
    project_slug: str = Query(..., description="Project slug (URL key)"),
    q: str | None = None,
    status: str | None = None,
    type_filter: str | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedLocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))

    filters: list[ColumnElement[bool]] = [SubstrateLocation.project_id == int(proj.id)]
    st = _status_expr(status)
    if st is not None:
        filters.append(st)
    if q:
        term = f"%{q.strip()}%"
        name_m = col(SubstrateLocation.name).ilike(term)
        norm_m = col(SubstrateLocation.normalized_name).ilike(term)
        filters.append(name_m | norm_m)
    if type_filter and type_filter != "all":
        filters.append(SubstrateLocation.location_type == type_filter)

    count_stmt = select(func.count()).select_from(SubstrateLocation).where(*filters)
    total_val = session.scalar(count_stmt)
    total = int(total_val or 0)

    list_stmt = (
        select(SubstrateLocation)
        .where(*filters)
        .order_by(col(SubstrateLocation.updated_at).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(session.exec(list_stmt).all())
    ids = [int(r.id) for r in rows if r.id is not None]
    mc = _mention_counts(session, ids)
    locs = [LocationResponse.from_row(r, mc.get(int(r.id), 0)) for r in rows]  # type: ignore[arg-type]

    page = offset // limit + 1 if limit else 1
    return PaginatedLocationResponse(
        locations=locs,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(locs) < total,
        has_prev=offset > 0,
    )


class LocationOptionsOut(BaseModel):
    locations: list[dict[str, Any]]


@router.get("/locations/options", response_model=LocationOptionsOut)
def list_location_options(
    project_slug: str = Query(...),
    q: str | None = None,
    status: str = Query("active"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationOptionsOut:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    filters = [SubstrateLocation.project_id == int(proj.id)]
    st = _status_expr(status)
    if st is not None:
        filters.append(st)
    if q:
        term = f"%{q.strip()}%"
        name_m = col(SubstrateLocation.name).ilike(term)
        norm_m = col(SubstrateLocation.normalized_name).ilike(term)
        filters.append(name_m | norm_m)
    stmt = (
        select(SubstrateLocation.id, SubstrateLocation.name, SubstrateLocation.location_type)
        .where(*filters)
        .order_by(col(SubstrateLocation.name))
        .offset(offset)
        .limit(limit)
    )
    raw = session.exec(stmt).all()
    return LocationOptionsOut(
        locations=[
            {
                "id": int(r[0]),  # type: ignore[index]
                "name": str(r[1]),
                "location_type": str(r[2] or ""),
            }
            for r in raw
        ]
    )


@router.get("/locations/{location_id}", response_model=LocationResponse)
def get_location(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    mc = _mention_counts(session, [location_id])
    return LocationResponse.from_row(loc, mc.get(location_id, 0))


@router.post("/locations", response_model=LocationResponse)
def create_location(
    body: CreateLocationBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    mapped = _map_incoming_status(body.status) or "provisional"
    ext_id = f"manual:{uuid.uuid4().hex}"
    row = SubstrateLocation(
        project_id=int(proj.id),
        name=body.name.strip(),
        normalized_name=_normalize_name(body.name),
        location_type=body.location_type.strip(),
        status=mapped,
        formatted_address=body.formatted_address,
        geometry_json=body.geometry_json,
        geometry_type=(body.geometry_json or {}).get("type") if body.geometry_json else None,
        external_source="stylebook_ui",
        external_id=ext_id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return LocationResponse.from_row(row, 0)


@router.patch("/locations/{location_id}", response_model=LocationResponse)
def patch_location(
    location_id: int,
    body: PatchLocationBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    if body.name is not None:
        loc.name = body.name.strip()
        loc.normalized_name = _normalize_name(body.name)
    if body.location_type is not None:
        loc.location_type = body.location_type.strip()
    if body.formatted_address is not None:
        loc.formatted_address = body.formatted_address
    if body.status is not None:
        loc.status = _map_incoming_status(body.status) or body.status
    session.add(loc)
    session.commit()
    session.refresh(loc)
    mc = _mention_counts(session, [location_id])
    return LocationResponse.from_row(loc, mc.get(location_id, 0))


@router.patch("/locations/{location_id}/geometry", response_model=LocationResponse)
def patch_location_geometry(
    location_id: int,
    body: PatchGeometryBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    loc.geometry_json = body.geometry_json
    loc.geometry_type = body.geometry_json.get("type") if body.geometry_json else None
    session.add(loc)
    session.commit()
    session.refresh(loc)
    mc = _mention_counts(session, [location_id])
    return LocationResponse.from_row(loc, mc.get(location_id, 0))


@router.patch("/canonical-locations/{canonical_id}/geometry")
def patch_canonical_location_geometry(
    canonical_id: int,
    body: PatchCanonicalGeometryBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Optional GeoJSON pin on a Stylebook canonical (proximity scoring)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    canon.geometry_json = body.geometry_json
    canon.geometry_type = body.geometry_json.get("type") if body.geometry_json else None
    session.add(canon)
    session.commit()
    return {"message": "updated", "id": int(canon.id)}  # type: ignore[arg-type]


@router.delete("/locations/{location_id}")
def delete_location(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        session.delete(loc)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Location still has linked mentions or references; cannot delete.",
        ) from None
    return {"message": "deleted", "candidates_created": 0, "links_deactivated": 0}


class LinkedMention(BaseModel):
    mention_id: int
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    original_text: str | None = None
    description: str | None = None
    location_name: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_type: str | None = None
    geometry_json: dict[str, Any] | None = None
    has_geometry: bool | None = None
    cache_id: int | None = None
    created_at: str | None = None
    link_location_cache_id: int | None = None
    link_location_mention_id: int | None = None


class LocationMentionsResponse(BaseModel):
    canonical_location_id: int
    canonical_name: str
    mentions: list[LinkedMention]
    total: int
    limit: int
    offset: int


@router.get("/locations/{location_id}/mentions", response_model=LocationMentionsResponse)
def list_location_mentions(
    location_id: int,
    project_slug: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(
        None,
        description="article | created_at (default)",
    ),
    sort_direction: str = Query("desc", description="asc or desc"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationMentionsResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")

    base_where: list[ColumnElement[bool]] = [
        SubstrateLocationMention.location_id == location_id,
        SubstrateLocationMention.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == int(proj.id),
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    count_stmt = (
        select(func.count())
        .select_from(SubstrateLocationMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .where(*base_where)
    )
    total = int(session.scalar(count_stmt) or 0)

    descending = sort_direction.strip().lower() != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstrateLocationMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    list_stmt = (
        select(SubstrateLocationMention, SubstrateArticle)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .where(*base_where)
        .order_by(order_by)
        .offset(offset)
        .limit(limit)
    )
    pairs = list(session.exec(list_stmt).all())
    mention_ids = [int(m.id) for m, _ in pairs if m.id is not None]  # type: ignore[union-attr]
    texts = _first_occurrence_mention_text_by_mention_id(session, mention_ids)

    mentions_out: list[LinkedMention] = []
    for mention, article in pairs:
        mid = int(mention.id)  # type: ignore[arg-type]
        aid = int(article.id)  # type: ignore[arg-type]
        created = mention.created_at
        mentions_out.append(
            LinkedMention(
                mention_id=mid,
                article_id=aid,
                article_headline=str(article.headline),
                article_url=article.url,
                original_text=texts.get(mid),
                description=mention.role_in_story,
                location_name=str(loc.name),
                location_type=loc.location_type,
                formatted_address=loc.formatted_address,
                geometry_type=loc.geometry_type,
                geometry_json=loc.geometry_json,
                has_geometry=bool(loc.geometry_json),
                cache_id=None,
                created_at=created.isoformat() if created else None,
                link_location_cache_id=None,
                link_location_mention_id=mid,
            )
        )

    return LocationMentionsResponse(
        canonical_location_id=location_id,
        canonical_name=str(loc.name),
        mentions=mentions_out,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/locations/{location_id}/mentions/{mention_id}/geometry")
def get_mention_geometry(
    location_id: int,
    mention_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    _ = mention_id
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    raise HTTPException(status_code=404, detail="Mention not found")


def _not_implemented() -> None:
    raise HTTPException(
        status_code=501,
        detail="This Stylebook action is not implemented on Backfield substrate yet.",
    )


@router.post("/locations/{location_id}/merge")
def merge_locations_stub(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = location_id
    _not_implemented()


@router.post("/locations/{location_id}/link")
def link_location_stub(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = location_id
    _not_implemented()


@router.post("/locations/{location_id}/unlink")
def unlink_location_stub(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = location_id
    _not_implemented()


@router.post("/locations/{location_id}/bulk-unlink")
def bulk_unlink_stub(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> None:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = location_id
    _not_implemented()
