"""Stylebook-scoped canonical locations (org Stylebooks; aggregate evidence)."""

from __future__ import annotations

from typing import Any

from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.locations import create_standalone_canonical
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, literal
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.mention_serialization import article_fields_for_linked_mention
from stylebook_api.routers.locations import _escape_ilike_metacharacters
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import (
    optional_project_filter_to_ids,
    require_stylebook_by_slug_in_auth_org,
)

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-canonicals"])


def _mention_counts_by_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocationMention.id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def _linked_substrate_counts(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocation.id)),
        )
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


class CanonicalLocationResponse(BaseModel):
    id: str
    slug: str
    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None
    geometry_type: str | None = None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0
    created_at: str
    updated_at: str

    @classmethod
    def from_row(
        cls,
        row: StylebookLocationCanonical,
        *,
        linked_substrate_count: int,
        mention_count: int,
    ) -> CanonicalLocationResponse:
        return cls(
            id=str(row.id),
            slug=str(row.slug),
            label=str(row.label),
            location_type=str(row.location_type) if row.location_type else None,
            formatted_address=row.formatted_address,
            geometry_json=row.geometry_json,
            geometry_type=row.geometry_type,
            status=str(row.status),
            linked_substrate_count=int(linked_substrate_count),
            mention_count=int(mention_count),
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
        )


class PaginatedCanonicalLocationResponse(BaseModel):
    canonicals: list[CanonicalLocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateCanonicalLocationBody(BaseModel):
    label: str = Field(min_length=1)
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_json: dict[str, Any] | None = None


class PatchCanonicalLocationBody(BaseModel):
    label: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    status: str | None = None


class PatchCanonicalGeometryBody(BaseModel):
    geometry_json: dict[str, Any] | None = None


def _canonical_filters(
    *, stylebook_id: int, q: str | None, type_filter: str | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [StylebookLocationCanonical.stylebook_id == stylebook_id]
    q_text = (q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(col(StylebookLocationCanonical.label).ilike(term, escape="\\"))
    if type_filter is not None:
        tf = type_filter.strip()
        if tf:
            filters.append(col(StylebookLocationCanonical.location_type) == tf)
    return filters


class LinkedSubstrateItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    location_type: str
    canonical_link_status: str
    formatted_address: str | None = None


class LinkedSubstratesResponse(BaseModel):
    substrates: list[LinkedSubstrateItem]


class LinkedMention(BaseModel):
    substrate_location_id: int
    mention_id: int
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    original_text: str | None = None
    mention_nature: str | None = None
    description: str | None = None
    location_name: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_type: str | None = None
    geometry_json: dict[str, Any] | None = None
    has_geometry: bool = False
    cache_id: str | None = None
    created_at: str | None = None
    link_location_cache_id: str | None = None
    link_location_mention_id: int | None = None


class LocationMentionsResponse(BaseModel):
    canonical_location_id: str
    canonical_name: str
    mentions: list[LinkedMention]
    total: int
    limit: int
    offset: int


def _first_occurrence_mention_text_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, str]:
    """First non-suppressed occurrence text per location mention (matches ``locations`` router)."""
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


@router.get(
    "/{stylebook_slug}/canonical-locations",
    response_model=PaginatedCanonicalLocationResponse,
)
def list_canonical_locations(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description=(
            "Optional project slug to filter evidence/counts "
            "(canonicals remain stylebook-scoped)."
        ),
    ),
    q: str | None = None,
    type_filter: str | None = Query(None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCanonicalLocationResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )

    filters = _canonical_filters(stylebook_id=int(sb.id), q=q, type_filter=type_filter)
    total = int(
        session.scalar(select(func.count()).select_from(StylebookLocationCanonical).where(*filters))
        or 0
    )

    label_lower = func.lower(col(StylebookLocationCanonical.label))
    label_col = col(StylebookLocationCanonical.label)
    q_text = (q or "").strip()
    if q_text:
        q_lower = q_text.lower()
        esc = _escape_ilike_metacharacters(q_text)
        prefix_pat = f"{esc}%"
        rank = case(
            (label_lower == literal(q_lower), 0),
            (label_col.ilike(prefix_pat, escape="\\"), 1),
            else_=2,
        )
        order_by = (
            rank.asc(),
            func.length(label_col).asc(),
            label_lower.asc(),
            col(StylebookLocationCanonical.id).asc(),
        )
    else:
        order_by = (label_lower.asc(), col(StylebookLocationCanonical.id).asc())

    rows = list(
        session.exec(
            select(StylebookLocationCanonical)
            .where(*filters)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    cids = [str(r.id) for r in rows if r.id is not None]
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=cids)
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=cids)
    out = [
        CanonicalLocationResponse.from_row(
            r,
            linked_substrate_count=lc.get(str(r.id), 0),
            mention_count=mc.get(str(r.id), 0),
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


@router.get("/{stylebook_slug}/canonical-locations/types")
def list_canonical_location_types(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    rows = session.exec(
        select(StylebookLocationCanonical.location_type).where(
            StylebookLocationCanonical.stylebook_id == int(sb.id),
            col(StylebookLocationCanonical.location_type).is_not(None),
            func.length(func.trim(col(StylebookLocationCanonical.location_type))) > 0,
        )
    ).all()
    types = sorted({str(r).strip() for r in rows if r is not None and str(r).strip()})
    return {"types": types}


@router.get(
    "/{stylebook_slug}/canonical-locations/{canonical_id}",
    response_model=CanonicalLocationResponse,
)
def get_canonical_location(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(
        None,
        description=(
            "Optional project slug to filter evidence/counts "
            "(default: all visible projects)."
        ),
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=[cid])
    return CanonicalLocationResponse.from_row(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.post(
    "/{stylebook_slug}/canonical-locations",
    response_model=CanonicalLocationResponse,
)
def create_canonical_location(
    stylebook_slug: str,
    body: CreateCanonicalLocationBody,
    project: str | None = Query(
        None,
        description="Optional project slug to filter evidence/counts in the response.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label is required")

    canon = create_standalone_canonical(
        session,
        stylebook_id=int(sb.id),
        label=label,
        location_type=body.location_type,
        formatted_address=body.formatted_address,
        geometry_json=body.geometry_json,
        provenance="stylebook_ui_manual",
    )
    session.commit()
    session.refresh(canon)

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=[cid])
    return CanonicalLocationResponse.from_row(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.patch(
    "/{stylebook_slug}/canonical-locations/{canonical_id}",
    response_model=CanonicalLocationResponse,
)
def patch_canonical_location(
    stylebook_slug: str,
    canonical_id: str,
    body: PatchCanonicalLocationBody,
    project: str | None = Query(
        None,
        description="Optional project slug to filter evidence/counts in the response.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalLocationResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
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
    if "status" in updates and updates["status"] is not None:
        canon.status = str(updates["status"]).strip().lower()

    session.add(canon)
    session.commit()
    session.refresh(canon)

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=[cid])
    return CanonicalLocationResponse.from_row(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.patch(
    "/{stylebook_slug}/canonical-locations/{canonical_id}/geometry",
    response_model=dict[str, str],
)
def patch_canonical_location_geometry(
    stylebook_slug: str,
    canonical_id: str,
    body: PatchCanonicalGeometryBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")
    canon.geometry_json = body.geometry_json
    session.add(canon)
    session.commit()
    return {"message": "ok", "id": str(canon.id)}


@router.delete("/{stylebook_slug}/canonical-locations/{canonical_id}")
def delete_canonical_location(
    stylebook_slug: str,
    canonical_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    # NOTE: deletion affects all projects referencing this canonical; keep admin-only for now.
    from backfield_auth.gate import require_org_admin

    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    require_org_admin(auth, int(sb.organization_id))

    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    # Unlink substrate rows across all projects in org for safety.
    pid_rows = session.exec(
        select(BackfieldProject.id).where(
            BackfieldProject.organization_id == int(sb.organization_id)
        )
    ).all()
    project_ids = [int(r) for r in pid_rows if r is not None]
    linked = session.exec(
        select(SubstrateLocation).where(
            col(SubstrateLocation.project_id).in_(project_ids),
            SubstrateLocation.stylebook_location_canonical_id == str(canon.id),
        )
    ).all()
    from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING

    for loc in linked:
        loc.stylebook_location_canonical_id = None
        loc.canonical_link_status = CANONICAL_LINK_PENDING
        loc.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": str(canon.id),
            }
        ]
        session.add(loc)

    session.delete(canon)
    session.commit()
    return {
        "message": "deleted",
        "id": str(canon.id),
        "unlinked_substrate_count": len(linked),
    }


@router.get(
    "/{stylebook_slug}/canonical-locations/{canonical_id}/linked-substrates",
    response_model=LinkedSubstratesResponse,
)
def list_canonical_linked_substrates(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(
        None,
        description="Optional project slug to filter substrates (default: all visible projects).",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkedSubstratesResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    rows = list(
        session.exec(
            select(SubstrateLocation)
            .where(
                col(SubstrateLocation.project_id).in_(project_ids),
                SubstrateLocation.stylebook_location_canonical_id == str(canon.id),
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
    "/{stylebook_slug}/canonical-locations/{canonical_id}/mentions",
    response_model=LocationMentionsResponse,
)
def list_canonical_location_mentions(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(
        None,
        description="Optional project slug to filter mentions (default: all visible projects).",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(None, description="article | created_at (default)"),
    sort_direction: str = Query("desc", description="asc or desc"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LocationMentionsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )

    base_where: list[ColumnElement[bool]] = [
        SubstrateLocation.stylebook_location_canonical_id == str(canon.id),
        col(SubstrateLocation.project_id).in_(project_ids),
        SubstrateLocationMention.deleted == False,  # noqa: E712
        col(SubstrateArticle.project_id).in_(project_ids),
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    total = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateLocationMention)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
            .where(*base_where)
        )
        or 0
    )

    descending = sort_direction.strip().lower() != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstrateLocationMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    triples = list(
        session.exec(
            select(SubstrateLocationMention, SubstrateArticle, SubstrateLocation)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
            .where(*base_where)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
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
        canonical_location_id=str(canon.id),
        canonical_name=str(canon.label),
        mentions=mentions_out,
        total=total,
        limit=limit,
        offset=offset,
    )

