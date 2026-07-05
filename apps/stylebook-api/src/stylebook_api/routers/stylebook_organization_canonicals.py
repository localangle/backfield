"""Stylebook-scoped canonical organizations (org Stylebooks; aggregate evidence)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from backfield_db import (
    BackfieldProject,
    StylebookOrganizationCanonical,
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_entities.activity import (
    EVENT_CANONICAL_CREATED,
    EVENT_CANONICAL_DELETED,
    EVENT_CANONICAL_UPDATED,
    log_stylebook_activity_safe,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.organization.persist import create_standalone_canonical
from backfield_entities.entities.organization.types import (
    ORGANIZATION_TYPE_VALUES,
    normalize_organization_type,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, exists, literal
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.mention_serialization import article_fields_for_linked_mention
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import (
    optional_project_filter_to_ids,
    require_stylebook_by_slug_in_auth_org,
)

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-organization-canonicals"])


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


def _escape_ilike_metacharacters(s: str) -> str:
    """Escape ``%`` and ``_`` for SQL ``ILIKE`` patterns (use with ``escape='\\\\'``)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _canonical_list_sort_key():
    return func.lower(col(StylebookOrganizationCanonical.label))


class CanonicalOrganizationResponse(BaseModel):
    """One ``stylebook_organization_canonical`` row (not a substrate organization)."""

    id: str
    slug: str
    label: str
    organization_type: str | None = None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_canonical(
        cls,
        canon: StylebookOrganizationCanonical,
        *,
        linked_substrate_count: int = 0,
        mention_count: int = 0,
    ) -> CanonicalOrganizationResponse:
        return cls(
            id=str(canon.id),
            slug=str(canon.slug),
            label=str(canon.label),
            organization_type=canon.organization_type,
            status=str(canon.status),
            linked_substrate_count=linked_substrate_count,
            mention_count=mention_count,
            created_at=canon.created_at,
            updated_at=canon.updated_at,
        )


class PaginatedCanonicalOrganizationResponse(BaseModel):
    canonicals: list[CanonicalOrganizationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateCanonicalOrganizationBody(BaseModel):
    """Create a catalog canonical only (no ``substrate_organization`` row)."""

    label: str
    organization_type: str | None = None


class PatchCanonicalOrganizationBody(BaseModel):
    label: str | None = None
    organization_type: str | None = None


def _mention_counts_by_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganizationMention.id)),
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
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
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganization.id)),
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def _canonical_filters(
    *,
    stylebook_id: int,
    q: str | None,
    type_filter: str | None,
    nature: str | None,
    project_ids: list[int],
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        StylebookOrganizationCanonical.stylebook_id == stylebook_id
    ]
    q_text = (q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(col(StylebookOrganizationCanonical.label).ilike(term, escape="\\"))
    if type_filter is not None:
        tf = type_filter.strip()
        if tf:
            filters.append(col(StylebookOrganizationCanonical.organization_type) == tf)
    if nature is not None:
        nf = nature.strip()
        if nf:
            filters.append(
                exists().where(
                    SubstrateOrganization.stylebook_organization_canonical_id
                    == StylebookOrganizationCanonical.id,
                    col(SubstrateOrganization.project_id).in_(project_ids),
                    SubstrateOrganizationMention.organization_id == SubstrateOrganization.id,
                    SubstrateOrganizationMention.deleted == False,  # noqa: E712
                    SubstrateOrganizationMention.nature == nf,
                )
            )
    return filters


def _min_mentions_subquery(*, project_ids: list[int], min_mentions: int) -> Any:
    return (
        select(SubstrateOrganization.stylebook_organization_canonical_id)
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_not(None),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
        .having(func.count(col(SubstrateOrganizationMention.id)) >= min_mentions)
    )


def _activity_order_columns(*, project_ids: list[int]) -> tuple[Any, ...]:
    max_sub_updated = (
        select(func.max(col(SubstrateOrganization.updated_at)))
        .where(
            col(SubstrateOrganization.stylebook_organization_canonical_id)
            == col(StylebookOrganizationCanonical.id),
            col(SubstrateOrganization.project_id).in_(project_ids),
        )
        .scalar_subquery()
    )
    canon_updated = col(StylebookOrganizationCanonical.updated_at)
    coalesced = func.coalesce(max_sub_updated, canon_updated)
    activity = case(
        (coalesced > canon_updated, coalesced),
        else_=canon_updated,
    )
    sort_key_col = _canonical_list_sort_key()
    return (activity.desc(), sort_key_col.asc(), col(StylebookOrganizationCanonical.id).asc())


class LinkedOrganizationSubstrateItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    organization_type: str | None = None
    canonical_link_status: str
    project_id: int
    project_slug: str
    project_name: str


class LinkedOrganizationSubstratesResponse(BaseModel):
    substrates: list[LinkedOrganizationSubstrateItem]


class LinkedOrganizationMention(BaseModel):
    substrate_organization_id: int
    mention_id: int
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    original_text: str | None = None
    mention_nature: str | None = None
    description: str | None = None
    organization_name: str
    organization_type: str | None = None
    created_at: str | None = None


class OrganizationMentionsResponse(BaseModel):
    canonical_organization_id: str
    canonical_name: str
    mentions: list[LinkedOrganizationMention]
    total: int
    limit: int
    offset: int


def _first_occurrence_mention_text_by_organization_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, str]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateOrganizationMentionOccurrence)
        .where(
            col(SubstrateOrganizationMentionOccurrence.organization_mention_id).in_(mention_ids),
            SubstrateOrganizationMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(SubstrateOrganizationMentionOccurrence.organization_mention_id),
            col(SubstrateOrganizationMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstrateOrganizationMentionOccurrence.id),
        )
    ).all()
    out: dict[int, str] = {}
    for occ in rows:
        mid = int(occ.organization_mention_id)
        if mid in out:
            continue
        txt = (occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


@router.get(
    "/{stylebook_slug}/canonical-organizations",
    response_model=PaginatedCanonicalOrganizationResponse,
)
def list_canonical_organizations(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to filter evidence/counts.",
    ),
    q: str | None = None,
    type_filter: str | None = Query(None),
    nature: str | None = Query(
        None,
        description="Filter to canonicals with at least one linked mention of this nature.",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: Literal["label", "recent"] = Query(
        "label",
        description="label (default): alphabetical; recent: latest linked activity.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCanonicalOrganizationResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )

    filters = _canonical_filters(
        stylebook_id=int(sb.id),
        q=q,
        type_filter=type_filter,
        nature=nature,
        project_ids=project_ids,
    )
    if min_mentions > 0:
        filters.append(
            col(StylebookOrganizationCanonical.id).in_(
                _min_mentions_subquery(project_ids=project_ids, min_mentions=min_mentions)
            )
        )

    total = int(
        session.scalar(
            select(func.count()).select_from(StylebookOrganizationCanonical).where(*filters)
        )
        or 0
    )

    label_lower = func.lower(col(StylebookOrganizationCanonical.label))
    label_col = col(StylebookOrganizationCanonical.label)
    sort_key_col = _canonical_list_sort_key()
    q_text = (q or "").strip()
    if sort == "recent":
        order_by = _activity_order_columns(project_ids=project_ids)
    elif q_text:
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
            sort_key_col.asc(),
            col(StylebookOrganizationCanonical.id).asc(),
        )
    else:
        order_by = (sort_key_col.asc(), col(StylebookOrganizationCanonical.id).asc())

    rows = list(
        session.exec(
            select(StylebookOrganizationCanonical)
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
        CanonicalOrganizationResponse.from_canonical(
            r,
            linked_substrate_count=lc.get(str(r.id), 0),
            mention_count=mc.get(str(r.id), 0),
        )
        for r in rows
    ]
    page = offset // limit + 1 if limit else 1
    return PaginatedCanonicalOrganizationResponse(
        canonicals=out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(out) < total,
        has_prev=offset > 0,
    )


@router.get("/{stylebook_slug}/canonical-organizations/types")
def list_canonical_organization_types(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    rows = session.exec(
        select(StylebookOrganizationCanonical.organization_type).where(
            StylebookOrganizationCanonical.stylebook_id == int(sb.id),
            col(StylebookOrganizationCanonical.organization_type).is_not(None),
            func.length(func.trim(col(StylebookOrganizationCanonical.organization_type))) > 0,
        )
    ).all()
    stored = {str(r).strip() for r in rows if r is not None and str(r).strip()}
    types = sorted(set(ORGANIZATION_TYPE_VALUES) | stored)
    return {"types": types}


@router.get(
    "/{stylebook_slug}/canonical-organizations/{canonical_id}",
    response_model=CanonicalOrganizationResponse,
)
def get_canonical_organization(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalOrganizationResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=[cid])
    return CanonicalOrganizationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.post(
    "/{stylebook_slug}/canonical-organizations",
    response_model=CanonicalOrganizationResponse,
)
def create_canonical_organization(
    stylebook_slug: str,
    body: CreateCanonicalOrganizationBody,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalOrganizationResponse:
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
        organization_type=normalize_organization_type(body.organization_type),
        provenance="stylebook_ui_manual",
    )
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_CREATED,
        entity_type="organization",
        entity_id=str(canon.id),
        entity_label=str(canon.label),
        payload_json={"organization_type": canon.organization_type},
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
    return CanonicalOrganizationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.patch(
    "/{stylebook_slug}/canonical-organizations/{canonical_id}",
    response_model=CanonicalOrganizationResponse,
)
def patch_canonical_organization(
    stylebook_slug: str,
    canonical_id: str,
    body: PatchCanonicalOrganizationBody,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalOrganizationResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        canon_uuid = UUID(canonical_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Canonical organization not found") from e
    canon = session.get(StylebookOrganizationCanonical, str(canon_uuid))
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")

    updates = body.model_dump(exclude_unset=True)
    if "label" in updates and updates["label"] is not None:
        canon.label = str(updates["label"]).strip()
    if "organization_type" in updates:
        v = updates["organization_type"]
        if v is None:
            canon.organization_type = None
        else:
            canon.organization_type = normalize_organization_type(str(v).strip() or None)

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_UPDATED,
        entity_type="organization",
        entity_id=str(canon.id),
        entity_label=str(canon.label),
        payload_json=updates,
    )
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
    return CanonicalOrganizationResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.delete("/{stylebook_slug}/canonical-organizations/{canonical_id}")
def delete_canonical_organization(
    stylebook_slug: str,
    canonical_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    from backfield_auth.gate import require_org_admin

    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    require_org_admin(session, auth, int(sb.organization_id))
    try:
        canon_uuid = UUID(canonical_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Canonical organization not found") from e
    canon = session.get(StylebookOrganizationCanonical, str(canon_uuid))
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")

    linked = session.exec(
        select(SubstrateOrganization).where(
            SubstrateOrganization.stylebook_organization_canonical_id == str(canon.id),
        )
    ).all()
    for organization in linked:
        organization.stylebook_organization_canonical_id = None
        organization.canonical_link_status = CANONICAL_LINK_PENDING
        organization.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": str(canon.id),
            }
        ]
        session.add(organization)

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_DELETED,
        entity_type="organization",
        entity_id=str(canon.id),
        entity_label=str(canon.label),
        payload_json={"unlinked_substrate_count": len(linked)},
    )
    session.delete(canon)
    session.commit()
    return {
        "message": "deleted",
        "id": str(canon.id),
        "unlinked_substrate_count": len(linked),
    }


@router.get(
    "/{stylebook_slug}/canonical-organizations/{canonical_id}/linked-substrates",
    response_model=LinkedOrganizationSubstratesResponse,
)
def list_canonical_linked_substrates(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkedOrganizationSubstratesResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    rows = list(
        session.exec(
            select(SubstrateOrganization, BackfieldProject)
            .join(BackfieldProject, BackfieldProject.id == SubstrateOrganization.project_id)
            .where(
                col(SubstrateOrganization.project_id).in_(project_ids),
                SubstrateOrganization.stylebook_organization_canonical_id == str(canon.id),
            )
            .order_by(
                func.lower(col(BackfieldProject.name)).asc(),
                func.lower(col(SubstrateOrganization.name)).asc(),
                col(SubstrateOrganization.id).asc(),
            )
        ).all()
    )
    return LinkedOrganizationSubstratesResponse(
        substrates=[
            LinkedOrganizationSubstrateItem(
                id=int(organization.id),  # type: ignore[arg-type]
                name=str(organization.name),
                normalized_name=str(organization.normalized_name or ""),
                organization_type=organization.organization_type,
                canonical_link_status=str(organization.canonical_link_status or ""),
                project_id=int(project_row.id),  # type: ignore[arg-type]
                project_slug=str(project_row.slug),
                project_name=str(project_row.name),
            )
            for organization, project_row in rows
        ]
    )


@router.get(
    "/{stylebook_slug}/canonical-organizations/{canonical_id}/mentions",
    response_model=OrganizationMentionsResponse,
)
def list_canonical_organization_mentions(
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
) -> OrganizationMentionsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )

    base_where: list[ColumnElement[bool]] = [
        SubstrateOrganization.stylebook_organization_canonical_id == str(canon.id),
        col(SubstrateOrganization.project_id).in_(project_ids),
        SubstrateOrganizationMention.deleted == False,  # noqa: E712
        col(SubstrateArticle.project_id).in_(project_ids),
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    total = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganizationMention)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(*base_where)
        )
        or 0
    )

    descending = sort_direction.strip().lower() != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstrateOrganizationMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    triples = list(
        session.exec(
            select(SubstrateOrganizationMention, SubstrateArticle, SubstrateOrganization)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(*base_where)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    texts = _first_occurrence_mention_text_by_organization_mention_id(session, mention_ids)

    mentions_out: list[LinkedOrganizationMention] = []
    for mention, article, organization in triples:
        mid = int(mention.id)  # type: ignore[arg-type]
        aid = int(article.id)  # type: ignore[arg-type]
        created = mention.created_at
        oid_sub = int(organization.id)  # type: ignore[arg-type]
        ah, au = article_fields_for_linked_mention(article)
        mentions_out.append(
            LinkedOrganizationMention(
                substrate_organization_id=oid_sub,
                mention_id=mid,
                article_id=aid,
                article_headline=ah,
                article_url=au,
                original_text=texts.get(mid),
                mention_nature=mention.nature,
                description=mention.role_in_story,
                organization_name=str(organization.name),
                organization_type=organization.organization_type,
                created_at=created.isoformat() if created else None,
            )
        )

    return OrganizationMentionsResponse(
        canonical_organization_id=str(canon.id),
        canonical_name=str(canon.label),
        mentions=mentions_out,
        total=total,
        limit=limit,
        offset=offset,
    )
