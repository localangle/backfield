"""Project-scoped substrate locations (Stylebook UI compatibility, ``project_slug``)."""

from __future__ import annotations

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
from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING
from backfield_stylebook.locations import create_standalone_canonical
from backfield_stylebook.place_extract_location_types import PLACE_EXTRACT_LOCATION_TYPES
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from backfield_stylebook.substrate_canonical_link_actions import (
    link_substrate_to_canonical_atomic,
    unlink_substrate_from_canonical,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.mention_serialization import article_fields_for_linked_mention

router = APIRouter(prefix="/v1", tags=["locations"])

_ALLOWED_CANONICAL_LIST_TYPE_FILTER = frozenset(PLACE_EXTRACT_LOCATION_TYPES)


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
    stylebook_location_canonical_id: int | None = None

    @classmethod
    def from_row(cls, row: SubstrateLocation, mention_count: int = 0) -> LocationResponse:
        lt = row.location_type or ""
        canon_fk = row.stylebook_location_canonical_id
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
            stylebook_location_canonical_id=int(canon_fk) if canon_fk is not None else None,
        )


class PaginatedLocationResponse(BaseModel):
    locations: list[LocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateCanonicalLocationBody(BaseModel):
    """Create a catalog canonical only (no ``substrate_location`` row)."""

    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None


class CreateLocationBody(BaseModel):
    """Legacy body for ``POST /v1/locations`` — maps ``name`` to canonical ``label``."""

    name: str
    location_type: str | None = Field(
        default=None,
        description="Optional; stored on the new ``stylebook_location_canonical`` row.",
    )
    formatted_address: str | None = Field(
        default=None,
        description="Optional; stored on the new ``stylebook_location_canonical`` row.",
    )
    geometry_json: dict[str, Any] | None = None
    status: str | None = Field(
        default=None,
        description="Ignored for catalog-only create (kept for API compatibility).",
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


def _persist_new_catalog_canonical(
    session: Session,
    *,
    project: BackfieldProject,
    label: str,
    geometry_json: dict[str, Any] | None,
    location_type: str | None = None,
    formatted_address: str | None = None,
) -> CanonicalLocationResponse:
    """Insert canonical + primary alias; no substrate row."""
    stylebook_id = _require_stylebook_id(session, project)
    canon = create_standalone_canonical(
        session,
        stylebook_id=stylebook_id,
        label=label,
        location_type=location_type,
        formatted_address=formatted_address,
        geometry_json=geometry_json,
        provenance="stylebook_ui_manual",
    )
    session.commit()
    session.refresh(canon)
    cid = int(canon.id)  # type: ignore[arg-type]
    mc = _mention_counts_by_canonical(session, project_id=int(project.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(project.id), canonical_ids=[cid])
    return CanonicalLocationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


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


def _mention_counts_by_canonical(
    session: Session, *, project_id: int, canonical_ids: list[int]
) -> dict[int, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocationMention.id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            SubstrateLocation.project_id == project_id,
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[int, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[int(cid)] = int(cnt)
    return out


def _linked_substrate_counts(
    session: Session, *, project_id: int, canonical_ids: list[int]
) -> dict[int, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocation.id)),
        )
        .where(
            SubstrateLocation.project_id == project_id,
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[int, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[int(cid)] = int(cnt)
    return out


class CanonicalLocationResponse(BaseModel):
    """One ``stylebook_location_canonical`` row (not a substrate location)."""

    id: int
    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None
    geometry_type: str | None = None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_canonical(
        cls,
        canon: StylebookLocationCanonical,
        *,
        linked_substrate_count: int = 0,
        mention_count: int = 0,
    ) -> CanonicalLocationResponse:
        return cls(
            id=int(canon.id),  # type: ignore[arg-type]
            label=str(canon.label),
            location_type=canon.location_type,
            formatted_address=canon.formatted_address,
            geometry_json=canon.geometry_json,
            geometry_type=canon.geometry_type,
            status=str(canon.status),
            linked_substrate_count=linked_substrate_count,
            mention_count=mention_count,
            created_at=canon.created_at,
            updated_at=canon.updated_at,
        )


class PaginatedCanonicalLocationResponse(BaseModel):
    canonicals: list[CanonicalLocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PatchCanonicalLocationBody(BaseModel):
    label: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None


class LinkedMention(BaseModel):
    """Mention row; ``substrate_location_id`` is the project ``substrate_location`` row."""

    substrate_location_id: int
    mention_id: int
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    original_text: str | None = None
    mention_nature: str | None = None
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


class LinkedSubstrateItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    location_type: str
    canonical_link_status: str
    formatted_address: str | None = None


class LinkedSubstratesResponse(BaseModel):
    substrates: list[LinkedSubstrateItem]


@router.get("/canonical-locations", response_model=PaginatedCanonicalLocationResponse)
def list_canonical_locations(
    project_slug: str = Query(...),
    q: str | None = None,
    type_filter: str | None = Query(
        None,
        description="Filter by canonical ``location_type`` (PlaceExtract taxonomy).",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCanonicalLocationResponse:
    """List Stylebook canonical locations for the project's Stylebook (deduplicated catalog)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)

    filters: list[ColumnElement[bool]] = [StylebookLocationCanonical.stylebook_id == stylebook_id]
    if q:
        term = f"%{q.strip()}%"
        filters.append(col(StylebookLocationCanonical.label).ilike(term))
    if type_filter is not None:
        tf = type_filter.strip()
        if tf:
            if tf not in _ALLOWED_CANONICAL_LIST_TYPE_FILTER:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid type_filter for canonical list",
                )
            filters.append(col(StylebookLocationCanonical.location_type) == tf)

    count_stmt = select(func.count()).select_from(StylebookLocationCanonical).where(*filters)
    total = int(session.scalar(count_stmt) or 0)

    list_stmt = (
        select(StylebookLocationCanonical)
        .where(*filters)
        .order_by(
            func.lower(col(StylebookLocationCanonical.label)).asc(),
            col(StylebookLocationCanonical.id).asc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = list(session.exec(list_stmt).all())
    cids = [int(r.id) for r in rows if r.id is not None]
    mc = _mention_counts_by_canonical(session, project_id=int(proj.id), canonical_ids=cids)
    lc = _linked_substrate_counts(session, project_id=int(proj.id), canonical_ids=cids)
    out = [
        CanonicalLocationResponse.from_canonical(
            r,
            linked_substrate_count=lc.get(int(r.id), 0),  # type: ignore[arg-type]
            mention_count=mc.get(int(r.id), 0),  # type: ignore[arg-type]
        )
        for r in rows
    ]
    page = offset // limit + 1 if limit else 1
    return PaginatedCanonicalLocationResponse(
        canonicals=out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(out) < total,
        has_prev=offset > 0,
    )


@router.post("/canonical-locations", response_model=CanonicalLocationResponse)
def create_canonical_location(
    body: CreateCanonicalLocationBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    """Create a Stylebook canonical (and primary alias) without a project substrate row."""
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label is required")
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return _persist_new_catalog_canonical(
        session,
        project=proj,
        label=label,
        geometry_json=body.geometry_json,
        location_type=body.location_type,
        formatted_address=body.formatted_address,
    )


@router.get("/canonical-locations/{canonical_id}", response_model=CanonicalLocationResponse)
def get_canonical_location(
    canonical_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    cid = int(canon.id)  # type: ignore[arg-type]
    mc = _mention_counts_by_canonical(session, project_id=int(proj.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(proj.id), canonical_ids=[cid])
    return CanonicalLocationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.get(
    "/canonical-locations/{canonical_id}/linked-substrates",
    response_model=LinkedSubstratesResponse,
)
def list_canonical_linked_substrates(
    canonical_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkedSubstratesResponse:
    """Project substrate rows currently linked to this Stylebook canonical."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    rows = list(
        session.exec(
            select(SubstrateLocation)
            .where(
                SubstrateLocation.project_id == int(proj.id),
                SubstrateLocation.stylebook_location_canonical_id == int(canonical_id),
            )
            .order_by(col(SubstrateLocation.name))
        ).all()
    )
    return LinkedSubstratesResponse(
        substrates=[
            LinkedSubstrateItem(
                id=int(r.id),  # type: ignore[arg-type]
                name=str(r.name),
                normalized_name=str(r.normalized_name or ""),
                location_type=str(r.location_type or ""),
                canonical_link_status=str(r.canonical_link_status or ""),
                formatted_address=(r.formatted_address or "").strip() or None,
            )
            for r in rows
        ]
    )


@router.get(
    "/canonical-locations/{canonical_id}/mentions",
    response_model=LocationMentionsResponse,
)
def list_canonical_location_mentions(
    canonical_id: int,
    project_slug: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(
        None,
        description="article | created_at (default)",
    ),
    sort_direction: str = Query("desc", description="asc or desc"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationMentionsResponse:
    """Mentions for all project substrate locations linked to this canonical."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    base_where: list[ColumnElement[bool]] = [
        SubstrateLocation.stylebook_location_canonical_id == canonical_id,
        SubstrateLocation.project_id == int(proj.id),
        SubstrateLocationMention.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == int(proj.id),
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    count_stmt = (
        select(func.count())
        .select_from(SubstrateLocationMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
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
        select(SubstrateLocationMention, SubstrateArticle, SubstrateLocation)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(*base_where)
        .order_by(order_by)
        .offset(offset)
        .limit(limit)
    )
    triples = list(session.exec(list_stmt).all())
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    texts = _first_occurrence_mention_text_by_mention_id(session, mention_ids)

    mentions_out: list[LinkedMention] = []
    for mention, article, loc in triples:
        mid = int(mention.id)  # type: ignore[arg-type]
        aid = int(article.id)  # type: ignore[arg-type]
        created = mention.created_at
        lid_sub = int(loc.id)  # type: ignore[arg-type]
        ah, au = article_fields_for_linked_mention(article)
        mentions_out.append(
            LinkedMention(
                substrate_location_id=lid_sub,
                mention_id=mid,
                article_id=aid,
                article_headline=ah,
                article_url=au,
                original_text=texts.get(mid),
                mention_nature=mention.nature,
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
        canonical_location_id=canonical_id,
        canonical_name=str(canon.label),
        mentions=mentions_out,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/canonical-locations/{canonical_id}", response_model=CanonicalLocationResponse)
def patch_canonical_location(
    canonical_id: int,
    body: PatchCanonicalLocationBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    updates = body.model_dump(exclude_unset=True)
    if "label" in updates and updates["label"] is not None:
        canon.label = str(updates["label"]).strip()
    if "location_type" in updates:
        v = updates["location_type"]
        if v is None:
            canon.location_type = None
        else:
            s = str(v).strip().lower()
            canon.location_type = s if s else None
    if "formatted_address" in updates:
        v = updates["formatted_address"]
        if v is None:
            canon.formatted_address = None
        else:
            s = str(v).strip()
            canon.formatted_address = s if s else None
    session.add(canon)
    session.commit()
    session.refresh(canon)
    cid = int(canon.id)  # type: ignore[arg-type]
    mc = _mention_counts_by_canonical(session, project_id=int(proj.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(proj.id), canonical_ids=[cid])
    return CanonicalLocationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.delete("/canonical-locations/{canonical_id}")
def delete_canonical_location(
    canonical_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Delete a Stylebook canonical; project substrate rows relink to the candidate queue."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    linked = session.exec(
        select(SubstrateLocation).where(
            SubstrateLocation.project_id == int(proj.id),
            SubstrateLocation.stylebook_location_canonical_id == canonical_id,
        )
    ).all()
    for loc in linked:
        loc.stylebook_location_canonical_id = None
        loc.canonical_link_status = CANONICAL_LINK_PENDING
        loc.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": int(canonical_id),
            }
        ]
        session.add(loc)

    session.delete(canon)
    session.commit()
    return {"message": "deleted", "id": canonical_id, "unlinked_substrate_count": len(linked)}


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


class LinkCanonicalBody(BaseModel):
    stylebook_location_canonical_id: int


class LinkCanonicalResponse(BaseModel):
    changed: bool


@router.post("/locations/{location_id}/unlink-canonical")
def unlink_substrate_from_canonical_route(
    location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        unlink_substrate_from_canonical(
            session, stylebook_id=stylebook_id, location=loc, provenance="stylebook_ui_unlink"
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session.commit()
    return {"message": "unlinked"}


@router.post("/locations/{location_id}/link-canonical", response_model=LinkCanonicalResponse)
def link_substrate_to_canonical_route(
    location_id: int,
    body: LinkCanonicalBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkCanonicalResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            location=loc,
            target_canonical_id=int(body.stylebook_location_canonical_id),
            provenance="stylebook_ui_link",
        )
    except ValueError as e:
        msg = str(e)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=409, detail=msg) from e
    session.commit()
    return LinkCanonicalResponse(changed=changed)


@router.post("/locations", response_model=CanonicalLocationResponse)
def create_location(
    body: CreateLocationBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    """Compatibility alias for :func:`create_canonical_location` (uses ``name`` as ``label``)."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return _persist_new_catalog_canonical(
        session,
        project=proj,
        label=name,
        geometry_json=body.geometry_json,
        location_type=body.location_type,
        formatted_address=body.formatted_address,
    )


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
        ah, au = article_fields_for_linked_mention(article)
        mentions_out.append(
            LinkedMention(
                substrate_location_id=int(location_id),
                mention_id=mid,
                article_id=aid,
                article_headline=ah,
                article_url=au,
                original_text=texts.get(mid),
                mention_nature=mention.nature,
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
