"""Stylebook-scoped canonical people (org Stylebooks; aggregate evidence)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from backfield_db import (
    BackfieldProject,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.activity import (
    EVENT_CANONICAL_CREATED,
    EVENT_CANONICAL_DELETED,
    EVENT_CANONICAL_UPDATED,
    log_stylebook_activity_safe,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.person.persist import create_standalone_canonical
from backfield_entities.entities.person.types import (
    PERSON_TYPE_VALUES,
    derive_person_sort_key,
    normalize_person_type,
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

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-person-canonicals"])


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


def _escape_ilike_metacharacters(s: str) -> str:
    """Escape ``%`` and ``_`` for SQL ``ILIKE`` patterns (use with ``escape='\\\\'``)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _canonical_list_sort_key():
    return func.coalesce(
        func.lower(col(StylebookPersonCanonical.sort_key)),
        func.lower(col(StylebookPersonCanonical.label)),
    )


def _person_list_sort_tiebreakers() -> tuple[Any, ...]:
    """Last-name order, then full label (first name) for shared sort keys."""
    return (
        _canonical_list_sort_key().asc(),
        func.lower(col(StylebookPersonCanonical.label)).asc(),
        col(StylebookPersonCanonical.id).asc(),
    )


class CanonicalPersonResponse(BaseModel):
    """One ``stylebook_person_canonical`` row (not a substrate person)."""

    id: str
    slug: str
    label: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    person_type: str | None = None
    sort_key: str | None = None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_canonical(
        cls,
        canon: StylebookPersonCanonical,
        *,
        linked_substrate_count: int = 0,
        mention_count: int = 0,
    ) -> CanonicalPersonResponse:
        return cls(
            id=str(canon.id),
            slug=str(canon.slug),
            label=str(canon.label),
            title=canon.title,
            affiliation=canon.affiliation,
            public_figure=bool(canon.public_figure),
            person_type=canon.person_type,
            sort_key=canon.sort_key,
            status=str(canon.status),
            linked_substrate_count=linked_substrate_count,
            mention_count=mention_count,
            created_at=canon.created_at,
            updated_at=canon.updated_at,
        )


class PaginatedCanonicalPersonResponse(BaseModel):
    canonicals: list[CanonicalPersonResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateCanonicalPersonBody(BaseModel):
    """Create a catalog canonical only (no ``substrate_person`` row)."""

    label: str
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    sort_key: str | None = None


class PatchCanonicalPersonBody(BaseModel):
    label: str | None = None
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    sort_key: str | None = None


def _mention_counts_by_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
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
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePerson.id)),
        )
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
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
    public_figure: bool | None,
    nature: str | None,
    title_filter: str | None = None,
    affiliation_filter: str | None = None,
    project_ids: list[int],
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [StylebookPersonCanonical.stylebook_id == stylebook_id]
    q_text = (q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(col(StylebookPersonCanonical.label).ilike(term, escape="\\"))
    if type_filter is not None:
        tf = type_filter.strip()
        if tf:
            filters.append(col(StylebookPersonCanonical.person_type) == tf)
    if public_figure is not None:
        filters.append(StylebookPersonCanonical.public_figure == public_figure)
    title_text = (title_filter or "").strip()
    if title_text:
        esc = _escape_ilike_metacharacters(title_text)
        filters.append(col(StylebookPersonCanonical.title).ilike(f"%{esc}%", escape="\\"))
    affiliation_text = (affiliation_filter or "").strip()
    if affiliation_text:
        esc = _escape_ilike_metacharacters(affiliation_text)
        filters.append(col(StylebookPersonCanonical.affiliation).ilike(f"%{esc}%", escape="\\"))
    if nature is not None:
        nf = nature.strip()
        if nf:
            filters.append(
                exists().where(
                    SubstratePerson.stylebook_person_canonical_id == StylebookPersonCanonical.id,
                    col(SubstratePerson.project_id).in_(project_ids),
                    SubstratePersonMention.person_id == SubstratePerson.id,
                    SubstratePersonMention.deleted == False,  # noqa: E712
                    SubstratePersonMention.nature == nf,
                )
            )
    return filters


def _min_mentions_subquery(*, project_ids: list[int], min_mentions: int) -> Any:
    return (
        select(SubstratePerson.stylebook_person_canonical_id)
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).is_not(None),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
        .having(func.count(col(SubstratePersonMention.id)) >= min_mentions)
    )


def _activity_order_columns(*, project_ids: list[int]) -> tuple[Any, ...]:
    max_sub_updated = (
        select(func.max(col(SubstratePerson.updated_at)))
        .where(
            col(SubstratePerson.stylebook_person_canonical_id) == col(StylebookPersonCanonical.id),
            col(SubstratePerson.project_id).in_(project_ids),
        )
        .scalar_subquery()
    )
    canon_updated = col(StylebookPersonCanonical.updated_at)
    coalesced = func.coalesce(max_sub_updated, canon_updated)
    activity = case(
        (coalesced > canon_updated, coalesced),
        else_=canon_updated,
    )
    return (activity.desc(), *_person_list_sort_tiebreakers())


class LinkedPersonSubstrateItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    mention_count: int = 0
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    canonical_link_status: str
    project_id: int
    project_slug: str
    project_name: str


class LinkedPersonSubstratesResponse(BaseModel):
    substrates: list[LinkedPersonSubstrateItem]


class LinkedPersonMention(BaseModel):
    substrate_person_id: int
    mention_id: int
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    original_text: str | None = None
    mention_nature: str | None = None
    description: str | None = None
    person_name: str
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    created_at: str | None = None


class PersonMentionsResponse(BaseModel):
    canonical_person_id: str
    canonical_name: str
    mentions: list[LinkedPersonMention]
    total: int
    limit: int
    offset: int


def _first_occurrence_mention_text_by_person_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, str]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstratePersonMentionOccurrence)
        .where(
            col(SubstratePersonMentionOccurrence.person_mention_id).in_(mention_ids),
            SubstratePersonMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(SubstratePersonMentionOccurrence.person_mention_id),
            col(SubstratePersonMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstratePersonMentionOccurrence.id),
        )
    ).all()
    out: dict[int, str] = {}
    for occ in rows:
        mid = int(occ.person_mention_id)
        if mid in out:
            continue
        txt = (occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


@router.get(
    "/{stylebook_slug}/canonical-people",
    response_model=PaginatedCanonicalPersonResponse,
)
def list_canonical_people(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to filter evidence/counts.",
    ),
    q: str | None = None,
    type_filter: str | None = Query(None),
    public_figure: bool | None = Query(None),
    title_filter: str | None = Query(
        None,
        description="Case-insensitive substring match on title.",
    ),
    affiliation_filter: str | None = Query(
        None,
        description="Case-insensitive substring match on affiliation.",
    ),
    nature: str | None = Query(
        None,
        description="Filter to canonicals with at least one linked mention of this nature.",
    ),
    min_mentions: int = Query(0, ge=0, le=1_000_000),
    sort: Literal["sort_key", "recent", "label"] = Query(
        "sort_key",
        description=(
            "sort_key (default): last-name order; recent: latest linked activity; "
            "label is a legacy alias for sort_key."
        ),
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCanonicalPersonResponse:
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
        public_figure=public_figure,
        nature=nature,
        title_filter=title_filter,
        affiliation_filter=affiliation_filter,
        project_ids=project_ids,
    )
    if min_mentions > 0:
        filters.append(
            col(StylebookPersonCanonical.id).in_(
                _min_mentions_subquery(project_ids=project_ids, min_mentions=min_mentions)
            )
        )

    total = int(
        session.scalar(select(func.count()).select_from(StylebookPersonCanonical).where(*filters))
        or 0
    )

    label_lower = func.lower(col(StylebookPersonCanonical.label))
    label_col = col(StylebookPersonCanonical.label)
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
            *_person_list_sort_tiebreakers(),
        )
    else:
        order_by = _person_list_sort_tiebreakers()

    rows = list(
        session.exec(
            select(StylebookPersonCanonical)
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
        CanonicalPersonResponse.from_canonical(
            r,
            linked_substrate_count=lc.get(str(r.id), 0),
            mention_count=mc.get(str(r.id), 0),
        )
        for r in rows
    ]
    page = offset // limit + 1 if limit else 1
    return PaginatedCanonicalPersonResponse(
        canonicals=out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(out) < total,
        has_prev=offset > 0,
    )


@router.get("/{stylebook_slug}/canonical-people/types")
def list_canonical_person_types(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    rows = session.exec(
        select(StylebookPersonCanonical.person_type).where(
            StylebookPersonCanonical.stylebook_id == int(sb.id),
            col(StylebookPersonCanonical.person_type).is_not(None),
            func.length(func.trim(col(StylebookPersonCanonical.person_type))) > 0,
        )
    ).all()
    stored = {str(r).strip() for r in rows if r is not None and str(r).strip()}
    types = sorted(set(PERSON_TYPE_VALUES) | stored)
    return {"types": types}


@router.get(
    "/{stylebook_slug}/canonical-people/{canonical_id}",
    response_model=CanonicalPersonResponse,
)
def get_canonical_person(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_ids=project_ids, canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_ids=project_ids, canonical_ids=[cid])
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.post(
    "/{stylebook_slug}/canonical-people",
    response_model=CanonicalPersonResponse,
)
def create_canonical_person(
    stylebook_slug: str,
    body: CreateCanonicalPersonBody,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
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
        title=body.title,
        affiliation=body.affiliation,
        public_figure=body.public_figure,
        person_type=normalize_person_type(body.person_type),
        sort_key=body.sort_key,
        provenance="stylebook_ui_manual",
    )
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_CREATED,
        entity_type="person",
        entity_id=str(canon.id),
        entity_label=str(canon.label),
        payload_json={"person_type": canon.person_type},
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
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.patch(
    "/{stylebook_slug}/canonical-people/{canonical_id}",
    response_model=CanonicalPersonResponse,
)
def patch_canonical_person(
    stylebook_slug: str,
    canonical_id: str,
    body: PatchCanonicalPersonBody,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        canon_uuid = UUID(canonical_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Canonical person not found") from e
    canon = session.get(StylebookPersonCanonical, str(canon_uuid))
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    updates = body.model_dump(exclude_unset=True)
    if "label" in updates and updates["label"] is not None:
        canon.label = str(updates["label"]).strip()
    if "person_type" in updates:
        v = updates["person_type"]
        if v is None:
            canon.person_type = None
        else:
            canon.person_type = normalize_person_type(str(v).strip() or None)
    if "title" in updates:
        v = updates["title"]
        if v is None:
            canon.title = None
        else:
            s = str(v).strip()
            canon.title = s if s else None
    if "affiliation" in updates:
        v = updates["affiliation"]
        if v is None:
            canon.affiliation = None
        else:
            s = str(v).strip()
            canon.affiliation = s if s else None
    if "public_figure" in updates and updates["public_figure"] is not None:
        canon.public_figure = bool(updates["public_figure"])
    if "sort_key" in updates:
        canon.sort_key = derive_person_sort_key(canon.label, explicit=updates["sort_key"])
    elif "label" in updates and updates["label"] is not None:
        canon.sort_key = derive_person_sort_key(canon.label)

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_UPDATED,
        entity_type="person",
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
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.delete("/{stylebook_slug}/canonical-people/{canonical_id}")
def delete_canonical_person(
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
        raise HTTPException(status_code=404, detail="Canonical person not found") from e
    canon = session.get(StylebookPersonCanonical, str(canon_uuid))
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    linked = session.exec(
        select(SubstratePerson).where(
            SubstratePerson.stylebook_person_canonical_id == str(canon.id),
        )
    ).all()
    for person in linked:
        person.stylebook_person_canonical_id = None
        person.canonical_link_status = CANONICAL_LINK_PENDING
        person.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": str(canon.id),
            }
        ]
        session.add(person)

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="manual_ui",
        event_type=EVENT_CANONICAL_DELETED,
        entity_type="person",
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
    "/{stylebook_slug}/canonical-people/{canonical_id}/linked-substrates",
    response_model=LinkedPersonSubstratesResponse,
)
def list_canonical_linked_substrates(
    stylebook_slug: str,
    canonical_id: str,
    project: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkedPersonSubstratesResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    rows = list(
        session.exec(
            select(SubstratePerson, BackfieldProject)
            .join(BackfieldProject, BackfieldProject.id == SubstratePerson.project_id)
            .where(
                col(SubstratePerson.project_id).in_(project_ids),
                SubstratePerson.stylebook_person_canonical_id == str(canon.id),
            )
            .order_by(
                func.lower(col(BackfieldProject.name)).asc(),
                func.lower(col(SubstratePerson.name)).asc(),
                col(SubstratePerson.id).asc(),
            )
        ).all()
    )
    person_ids = [int(person.id) for person, _ in rows if person.id is not None]  # type: ignore[arg-type]
    mention_counts: dict[int, int] = {}
    if person_ids:
        mention_counts = {
            int(person_id): int(count or 0)
            for person_id, count in session.exec(
                select(
                    col(SubstratePersonMention.person_id),
                    func.count(col(SubstratePersonMention.id)),
                )
                .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
                .where(
                    col(SubstratePersonMention.person_id).in_(person_ids),
                    SubstratePersonMention.deleted == False,  # noqa: E712
                    col(SubstrateArticle.project_id).in_(project_ids),
                    SubstrateArticle.deleted == False,  # noqa: E712
                )
                .group_by(col(SubstratePersonMention.person_id))
            ).all()
        }
    return LinkedPersonSubstratesResponse(
        substrates=[
            LinkedPersonSubstrateItem(
                id=int(person.id),  # type: ignore[arg-type]
                name=str(person.name),
                normalized_name=str(person.normalized_name or ""),
                mention_count=mention_counts.get(int(person.id), 0),  # type: ignore[arg-type]
                person_type=person.person_type,
                title=(person.title or "").strip() or None,
                affiliation=(person.affiliation or "").strip() or None,
                public_figure=bool(person.public_figure),
                canonical_link_status=str(person.canonical_link_status or ""),
                project_id=int(project_row.id),  # type: ignore[arg-type]
                project_slug=str(project_row.slug),
                project_name=str(project_row.name),
            )
            for person, project_row in rows
        ]
    )


@router.get(
    "/{stylebook_slug}/canonical-people/{canonical_id}/mentions",
    response_model=PersonMentionsResponse,
)
def list_canonical_person_mentions(
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
) -> PersonMentionsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )

    base_where: list[ColumnElement[bool]] = [
        SubstratePerson.stylebook_person_canonical_id == str(canon.id),
        col(SubstratePerson.project_id).in_(project_ids),
        SubstratePersonMention.deleted == False,  # noqa: E712
        col(SubstrateArticle.project_id).in_(project_ids),
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    total = int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePersonMention)
            .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
            .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
            .where(*base_where)
        )
        or 0
    )

    descending = sort_direction.strip().lower() != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstratePersonMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    triples = list(
        session.exec(
            select(SubstratePersonMention, SubstrateArticle, SubstratePerson)
            .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
            .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
            .where(*base_where)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    texts = _first_occurrence_mention_text_by_person_mention_id(session, mention_ids)

    mentions_out: list[LinkedPersonMention] = []
    for mention, article, person in triples:
        mid = int(mention.id)  # type: ignore[arg-type]
        aid = int(article.id)  # type: ignore[arg-type]
        created = mention.created_at
        pid_sub = int(person.id)  # type: ignore[arg-type]
        ah, au = article_fields_for_linked_mention(article)
        mentions_out.append(
            LinkedPersonMention(
                substrate_person_id=pid_sub,
                mention_id=mid,
                article_id=aid,
                article_headline=ah,
                article_url=au,
                original_text=texts.get(mid),
                mention_nature=mention.nature,
                description=mention.role_in_story,
                person_name=str(person.name),
                person_type=person.person_type,
                title=(person.title or "").strip() or None,
                affiliation=(person.affiliation or "").strip() or None,
                created_at=created.isoformat() if created else None,
            )
        )

    return PersonMentionsResponse(
        canonical_person_id=str(canon.id),
        canonical_name=str(canon.label),
        mentions=mentions_out,
        total=total,
        limit=limit,
        offset=offset,
    )
