"""Project-scoped canonical people (Stylebook UI compatibility, ``project_slug``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING
from backfield_stylebook.entities.person.persist import (
    requeue_substrate_after_story_remove,
    unlink_substrate_from_canonical,
)
from backfield_stylebook.entities.person.types import (
    PERSON_NATURE_VALUES,
    person_identity_fingerprint,
)
from backfield_stylebook.people import (
    create_standalone_canonical,
    link_substrate_to_canonical_atomic,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, exists, literal
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id

router = APIRouter(prefix="/v1", tags=["people"])


def _escape_ilike_metacharacters(s: str) -> str:
    """Escape ``%`` and ``_`` for SQL ``ILIKE`` patterns (use with ``escape='\\\\'``)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    return project_by_slug(session, slug)


def _require_stylebook_id(
    session: Session,
    project: BackfieldProject,
    stylebook_slug: str | None = None,
) -> int:
    return require_stylebook_id(session, project, stylebook_slug=stylebook_slug)


def _mention_counts_by_canonical(
    session: Session, *, project_id: int, canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            SubstratePerson.project_id == project_id,
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
    session: Session, *, project_id: int, canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePerson.id)),
        )
        .where(
            SubstratePerson.project_id == project_id,
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


class CanonicalPersonResponse(BaseModel):
    """One ``stylebook_person_canonical`` row (not a substrate person)."""

    id: str
    slug: str
    label: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    person_type: str | None = None
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


class PatchCanonicalPersonBody(BaseModel):
    label: str | None = None
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None


class LinkedSubstrateItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    person_type: str
    canonical_link_status: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False


class LinkedSubstratesResponse(BaseModel):
    substrates: list[LinkedSubstrateItem]


class LinkCanonicalBody(BaseModel):
    stylebook_person_canonical_id: UUID


class LinkCanonicalResponse(BaseModel):
    changed: bool


def _persist_new_catalog_canonical(
    session: Session,
    *,
    project: BackfieldProject,
    label: str,
    person_type: str | None = None,
    title: str | None = None,
    affiliation: str | None = None,
    public_figure: bool = False,
    stylebook_slug: str | None = None,
) -> CanonicalPersonResponse:
    """Insert canonical + primary alias; no substrate row."""
    stylebook_id = _require_stylebook_id(session, project, stylebook_slug)
    canon = create_standalone_canonical(
        session,
        stylebook_id=stylebook_id,
        label=label,
        title=title,
        affiliation=affiliation,
        public_figure=public_figure,
        person_type=person_type,
        provenance="stylebook_ui_manual",
    )
    session.commit()
    session.refresh(canon)
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_id=int(project.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(project.id), canonical_ids=[cid])
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


def _nature_filter_exists(project_id: int, nature: str) -> ColumnElement[bool]:
    return exists().where(
        SubstratePerson.stylebook_person_canonical_id == StylebookPersonCanonical.id,
        SubstratePerson.project_id == project_id,
        SubstratePersonMention.person_id == SubstratePerson.id,
        SubstratePersonMention.deleted == False,  # noqa: E712
        SubstratePersonMention.nature == nature,
    )


@router.get("/canonical-people", response_model=PaginatedCanonicalPersonResponse)
def list_canonical_people(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = None,
    type_filter: str | None = Query(
        None,
        description="Filter by canonical ``person_type``.",
    ),
    public_figure: bool | None = Query(None, description="Filter by public figure flag."),
    nature_filter: str | None = Query(
        None,
        description="Filter to canonicals with at least one linked mention of this nature.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCanonicalPersonResponse:
    """List Stylebook canonical people for the project's Stylebook (deduplicated catalog)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    project_id = int(proj.id)

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
    if nature_filter is not None:
        nf = nature_filter.strip()
        if nf:
            filters.append(_nature_filter_exists(project_id, nf))

    count_stmt = select(func.count()).select_from(StylebookPersonCanonical).where(*filters)
    total = int(session.scalar(count_stmt) or 0)

    label_lower = func.lower(col(StylebookPersonCanonical.label))
    label_col = col(StylebookPersonCanonical.label)
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
            col(StylebookPersonCanonical.id).asc(),
        )
    else:
        order_by = (label_lower.asc(), col(StylebookPersonCanonical.id).asc())

    list_stmt = (
        select(StylebookPersonCanonical)
        .where(*filters)
        .order_by(*order_by)
        .offset(offset)
        .limit(limit)
    )
    rows = list(session.exec(list_stmt).all())
    cids = [str(r.id) for r in rows if r.id is not None]
    mc = _mention_counts_by_canonical(session, project_id=project_id, canonical_ids=cids)
    lc = _linked_substrate_counts(session, project_id=project_id, canonical_ids=cids)
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


@router.get("/canonical-people/types")
def list_canonical_person_types(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Return distinct canonical ``person_type`` values for filter dropdowns."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    rows = session.exec(
        select(func.distinct(StylebookPersonCanonical.person_type)).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            col(StylebookPersonCanonical.person_type).is_not(None),
            func.length(func.trim(col(StylebookPersonCanonical.person_type))) > 0,
        )
    ).all()
    types = sorted({str(r).strip() for r in rows if r is not None and str(r).strip()})
    return {"types": types}


@router.post("/canonical-people", response_model=CanonicalPersonResponse)
def create_canonical_person(
    body: CreateCanonicalPersonBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
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
        person_type=body.person_type,
        title=body.title,
        affiliation=body.affiliation,
        public_figure=body.public_figure,
        stylebook_slug=stylebook_slug,
    )


@router.get("/canonical-people/{canonical_id}", response_model=CanonicalPersonResponse)
def get_canonical_person(
    canonical_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_id=int(proj.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(proj.id), canonical_ids=[cid])
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.get(
    "/canonical-people/{canonical_id}/linked-substrates",
    response_model=LinkedSubstratesResponse,
)
def list_canonical_linked_substrates(
    canonical_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkedSubstratesResponse:
    """Project substrate rows currently linked to this Stylebook canonical."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    rows = list(
        session.exec(
            select(SubstratePerson)
            .where(
                SubstratePerson.project_id == int(proj.id),
                SubstratePerson.stylebook_person_canonical_id == str(canonical_id),
            )
            .order_by(col(SubstratePerson.name))
        ).all()
    )
    return LinkedSubstratesResponse(
        substrates=[
            LinkedSubstrateItem(
                id=int(r.id),  # type: ignore[arg-type]
                name=str(r.name),
                normalized_name=str(r.normalized_name or ""),
                person_type=str(r.person_type or ""),
                canonical_link_status=str(r.canonical_link_status or ""),
                title=(r.title or "").strip() or None,
                affiliation=(r.affiliation or "").strip() or None,
                public_figure=bool(r.public_figure),
            )
            for r in rows
        ]
    )


@router.patch("/canonical-people/{canonical_id}", response_model=CanonicalPersonResponse)
def patch_canonical_person(
    canonical_id: UUID,
    body: PatchCanonicalPersonBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CanonicalPersonResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")
    updates = body.model_dump(exclude_unset=True)
    if "label" in updates and updates["label"] is not None:
        canon.label = str(updates["label"]).strip()
    if "person_type" in updates:
        v = updates["person_type"]
        if v is None:
            canon.person_type = None
        else:
            s = str(v).strip()
            canon.person_type = s if s else None
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
    session.add(canon)
    session.commit()
    session.refresh(canon)
    cid = str(canon.id)
    mc = _mention_counts_by_canonical(session, project_id=int(proj.id), canonical_ids=[cid])
    lc = _linked_substrate_counts(session, project_id=int(proj.id), canonical_ids=[cid])
    return CanonicalPersonResponse.from_canonical(
        canon,
        linked_substrate_count=lc.get(cid, 0),
        mention_count=mc.get(cid, 0),
    )


@router.delete("/canonical-people/{canonical_id}")
def delete_canonical_person(
    canonical_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Delete a Stylebook canonical; project substrate rows relink to the candidate queue."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    linked = session.exec(
        select(SubstratePerson).where(
            SubstratePerson.project_id == int(proj.id),
            SubstratePerson.stylebook_person_canonical_id == str(canonical_id),
        )
    ).all()
    for person in linked:
        person.stylebook_person_canonical_id = None
        person.canonical_link_status = CANONICAL_LINK_PENDING
        person.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": str(canonical_id),
            }
        ]
        session.add(person)

    session.delete(canon)
    session.commit()
    return {
        "message": "deleted",
        "id": str(canonical_id),
        "unlinked_substrate_count": len(linked),
    }


@router.post("/people/{person_id}/unlink-canonical")
def unlink_substrate_from_canonical_route(
    person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")
    try:
        unlink_substrate_from_canonical(
            session, stylebook_id=stylebook_id, person=person, provenance="stylebook_ui_unlink"
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session.commit()
    return {"message": "unlinked"}


@router.post("/people/{person_id}/link-canonical", response_model=LinkCanonicalResponse)
def link_substrate_to_canonical_route(
    person_id: int,
    body: LinkCanonicalBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkCanonicalResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")
    try:
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            person=person,
            target_canonical_id=str(body.stylebook_person_canonical_id),
            provenance="stylebook_ui_link",
        )
    except ValueError as e:
        msg = str(e)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=409, detail=msg) from e
    session.commit()
    return LinkCanonicalResponse(changed=changed)


def _normalize_person_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class SubstratePersonResponse(BaseModel):
    id: int
    name: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    person_type: str | None = None
    status: str
    canonical_link_status: str | None = None
    stylebook_person_canonical_id: str | None = None


class PatchSubstratePersonBody(BaseModel):
    name: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    person_type: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] | None = None


class CreatePersonFromArticleEvidenceBody(BaseModel):
    article_id: int
    run_id: str
    name: str
    mention_text: str
    quote_text: str
    start_char: int
    end_char: int
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    nature: str | None = None
    role_in_story: str | None = None


class CreatePersonFromArticleEvidenceResponse(BaseModel):
    person: SubstratePersonResponse
    mention_id: int
    occurrence_id: int
    anchor: str


@router.post(
    "/people/from-article-evidence",
    response_model=CreatePersonFromArticleEvidenceResponse,
)
def create_person_from_article_evidence(
    body: CreatePersonFromArticleEvidenceBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CreatePersonFromArticleEvidenceResponse:
    """Create a saved person from a manually selected article passage."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))

    name = body.name.strip()
    mention_text = body.mention_text.strip()
    quote_text = body.quote_text.strip()
    run_id = body.run_id.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not mention_text:
        raise HTTPException(status_code=400, detail="mention_text is required")
    if not quote_text:
        raise HTTPException(status_code=400, detail="quote_text is required")
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    if body.end_char <= body.start_char:
        raise HTTPException(status_code=400, detail="end_char must be after start_char")

    article = session.get(SubstrateArticle, body.article_id)
    if article is None or int(article.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Article not found")
    article_text = str(article.text or "")
    if body.end_char > len(article_text):
        raise HTTPException(status_code=400, detail="source selection is outside the article")
    selected_text = article_text[body.start_char : body.end_char]
    if selected_text != quote_text:
        raise HTTPException(status_code=400, detail="source selection does not match the article")

    person_type = body.person_type.strip() if body.person_type else None
    title = body.title.strip() if body.title else None
    affiliation = body.affiliation.strip() if body.affiliation else None
    normalized_name = _normalize_person_name(name)
    nature: str | None = None
    if body.nature is not None:
        nature_raw = body.nature.strip().lower()
        nature = nature_raw if nature_raw in PERSON_NATURE_VALUES else "other"

    person = SubstratePerson(
        project_id=int(proj.id),
        name=name,
        normalized_name=normalized_name,
        title=title,
        affiliation=affiliation,
        public_figure=bool(body.public_figure),
        person_type=person_type,
        status="active",
        canonical_link_status=CANONICAL_LINK_PENDING,
        source_kind="manual_add",
        source_details_json={
            "source": "agate_review_add_person",
            "run_id": run_id,
        },
        identity_fingerprint=person_identity_fingerprint(
            normalized_name=normalized_name,
            title=title,
            affiliation=affiliation,
        ),
    )
    session.add(person)
    session.flush()
    if person.id is None:
        raise HTTPException(status_code=500, detail="Person could not be created")
    anchor = f"user_person:{int(person.id)}"
    person.source_details_json = {
        "source": "agate_review_add_person",
        "run_id": run_id,
        "raw_entry_id": anchor,
    }

    mention = SubstratePersonMention(
        article_id=int(article.id),  # type: ignore[arg-type]
        person_id=int(person.id),
        role_in_story=body.role_in_story.strip() if body.role_in_story else None,
        nature=nature,
        added=True,
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_person", "run_id": run_id},
    )
    session.add(mention)
    session.flush()
    if mention.id is None:
        raise HTTPException(status_code=500, detail="Person mention could not be created")

    occurrence = SubstratePersonMentionOccurrence(
        person_mention_id=int(mention.id),
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_person", "run_id": run_id},
        mention_text=mention_text,
        quote_text=quote_text,
        start_char=body.start_char,
        end_char=body.end_char,
        occurrence_order=0,
        labels_json=[],
        suppressed=False,
    )
    session.add(occurrence)
    session.commit()
    session.refresh(person)
    session.refresh(mention)
    session.refresh(occurrence)

    return CreatePersonFromArticleEvidenceResponse(
        person=SubstratePersonResponse(
            id=int(person.id),  # type: ignore[arg-type]
            name=str(person.name),
            title=person.title,
            affiliation=person.affiliation,
            public_figure=bool(person.public_figure),
            person_type=person.person_type,
            status=str(person.status),
            canonical_link_status=str(person.canonical_link_status or ""),
            stylebook_person_canonical_id=person.stylebook_person_canonical_id,
        ),
        mention_id=int(mention.id),  # type: ignore[arg-type]
        occurrence_id=int(occurrence.id),  # type: ignore[arg-type]
        anchor=anchor,
    )


@router.patch("/people/{person_id}", response_model=SubstratePersonResponse)
def patch_substrate_person(
    person_id: int,
    body: PatchSubstratePersonBody,
    project_slug: str = Query(...),
    article_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstratePersonResponse:
    """Update a substrate person (and optional article mention editorial fields)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        person.name = name
        person.normalized_name = _normalize_person_name(name)
    if body.title is not None:
        person.title = body.title.strip() or None
    if body.affiliation is not None:
        person.affiliation = body.affiliation.strip() or None
    if body.public_figure is not None:
        person.public_figure = bool(body.public_figure)
    if body.person_type is not None:
        person.person_type = body.person_type.strip() or None

    person.identity_fingerprint = person_identity_fingerprint(
        normalized_name=str(person.normalized_name),
        title=person.title,
        affiliation=person.affiliation,
    )
    session.add(person)

    if article_id is not None:
        mention = session.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.article_id == article_id,
                SubstratePersonMention.person_id == person_id,
                col(SubstratePersonMention.deleted).is_(False),
            )
        ).first()
        if mention is not None:
            if body.role_in_story is not None:
                mention.role_in_story = body.role_in_story.strip() or None
            if body.nature is not None:
                nature = body.nature.strip().lower()
                mention.nature = nature if nature in PERSON_NATURE_VALUES else "other"
            if body.nature_secondary_tags is not None:
                tags = [
                    t.strip().lower()
                    for t in body.nature_secondary_tags
                    if isinstance(t, str) and t.strip()
                ]
                mention.nature_secondary_tags_json = [
                    t for t in tags if t in PERSON_NATURE_VALUES
                ] or None
            mention.edited = True
            session.add(mention)

    session.commit()
    session.refresh(person)
    return SubstratePersonResponse(
        id=int(person.id),  # type: ignore[arg-type]
        name=str(person.name),
        title=person.title,
        affiliation=person.affiliation,
        public_figure=bool(person.public_figure),
        person_type=person.person_type,
        status=str(person.status),
        canonical_link_status=str(person.canonical_link_status or ""),
        stylebook_person_canonical_id=person.stylebook_person_canonical_id,
    )


@router.delete("/people/{person_id}")
def delete_substrate_person(
    person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    article_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Soft-delete story mentions; remove substrate row when no active mentions remain."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")

    mention_filters: list[ColumnElement[bool]] = [
        SubstratePersonMention.person_id == person_id,
        SubstratePersonMention.deleted == False,  # noqa: E712
    ]
    if article_id is not None:
        mention_filters.append(SubstratePersonMention.article_id == article_id)

    mentions = session.exec(select(SubstratePersonMention).where(*mention_filters)).all()
    for mention in mentions:
        mention.deleted = True
        session.add(mention)
    session.flush()

    remaining = int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePersonMention)
            .where(
                SubstratePersonMention.person_id == person_id,
                SubstratePersonMention.deleted == False,  # noqa: E712
            )
        )
        or 0
    )

    person_deleted = False
    candidates_created = 0
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    if remaining == 0:
        if requeue_substrate_after_story_remove(
            session,
            stylebook_id=stylebook_id,
            person=person,
            provenance="agate_review_delete",
        ):
            candidates_created = 1
        session.delete(person)
        person_deleted = True

    session.commit()
    return {
        "message": "deleted",
        "mentions_removed": len(mentions),
        "person_deleted": person_deleted,
        "candidates_created": candidates_created,
    }

