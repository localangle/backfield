"""Person candidate queue: substrate rows not yet linked to a Stylebook canonical."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.candidate_review import (
    strip_ai_recommendations_from_review_reasons,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.entities.person.persist import (
    link_substrate_to_canonical_atomic,
    materialize_new_canonical_and_link,
    rank_canonical_suggestions_for_substrate,
    refresh_aliases_for_linked_person,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, or_
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.candidate_review_display import (
    first_candidate_review_line,
    format_candidate_review_lines,
)
from stylebook_api.helpers.project_scope import (
    project_by_slug as _project_by_slug,
)
from stylebook_api.helpers.project_scope import (
    require_stylebook_id as _require_stylebook_id,
)
from stylebook_api.mention_serialization import article_fields_for_linked_mention

router = APIRouter(prefix="/v1/people", tags=["person-candidates"])


def _substrate_list_sort_key():
    return func.coalesce(col(SubstratePerson.sort_key), col(SubstratePerson.normalized_name))


class PaginatedCandidatesResponse(BaseModel):
    candidates: list[dict[str, Any]]
    total: int
    has_next: bool
    has_prev: bool


class CandidateContextItem(BaseModel):
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    text: str


class CandidateContextResponse(BaseModel):
    substrate_person_id: int
    created_at: str | None = None
    note: str | None = None
    examples: list[CandidateContextItem]


class UpdateCandidateNoteBody(BaseModel):
    note: str | None = None


def _open_candidate_filters(
    project_id: int,
    *,
    needs_review: bool | None,
    q: str | None,
    type_filter: str | None,
) -> list[Any]:
    filters: list[Any] = [
        SubstratePerson.project_id == project_id,
        col(SubstratePerson.stylebook_person_canonical_id).is_(None),
        SubstratePerson.canonical_link_status == CANONICAL_LINK_PENDING,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstratePerson.name).ilike(term),
                col(SubstratePerson.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstratePerson.person_type == tf)
    if needs_review is True:
        filters.append(
            exists().where(
                SubstratePersonMention.person_id == SubstratePerson.id,
                SubstratePersonMention.deleted == False,  # noqa: E712
                SubstratePersonMention.needs_review == True,  # noqa: E712
            )
        )
    return filters


def _deferred_candidate_filters(
    project_id: int, *, q: str | None, type_filter: str | None
) -> list[Any]:
    filters: list[Any] = [
        SubstratePerson.project_id == project_id,
        col(SubstratePerson.stylebook_person_canonical_id).is_(None),
        SubstratePerson.canonical_link_status == CANONICAL_LINK_WAIVED,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstratePerson.name).ilike(term),
                col(SubstratePerson.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstratePerson.person_type == tf)
    return filters


def _canonical_suggestion_payload(person: SubstratePerson) -> dict[str, Any] | None:
    """Merge rules-plan + adjudication blobs for Stylebook UI (ingest recommendations)."""
    raw = person.canonical_review_reasons_json
    if raw is None:
        return None
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        items = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        items = [raw]
    sug: dict[str, Any] | None = None
    adj: dict[str, Any] | None = None
    for it in items:
        code = str(it.get("code") or "")
        if code == "canonical_suggestion":
            sug = dict(it)
        if code == "canonical_adjudication":
            adj = dict(it)
    if sug is None and adj is None:
        return None
    out: dict[str, Any] = {}
    if sug is not None:
        out["suggested_action"] = sug.get("suggested_action")
        cid = sug.get("stylebook_person_canonical_id")
        out["stylebook_person_canonical_id"] = str(cid) if cid is not None else None
        out["source"] = sug.get("source")
    if adj is not None:
        out["adjudication_confidence"] = adj.get("confidence")
        out["adjudication_rationale"] = adj.get("rationale")
        out["adjudication_model"] = adj.get("model")
        out["adjudication_outcome"] = adj.get("outcome")
        if (
            out.get("stylebook_person_canonical_id") is None
            and adj.get("canonical_id") is not None
        ):
            raw_c = adj.get("canonical_id")
            if raw_c is not None:
                out["stylebook_person_canonical_id"] = str(raw_c).strip() or None
        if out.get("suggested_action") is None:
            outcome = str(adj.get("outcome") or "").strip()
            if outcome == "link_existing" and out.get("stylebook_person_canonical_id"):
                out["suggested_action"] = "link_existing"
            elif outcome == "no_high_confidence_link":
                out["suggested_action"] = "materialize_new"
    return out or None


def _extract_review_note(person: SubstratePerson) -> str | None:
    raw = person.canonical_review_reasons_json
    if raw is None:
        return None
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        items = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        items = [raw]
    for it in reversed(items):
        if str(it.get("code") or "") == "review_note":
            val = (it.get("note") or "").strip()
            return val or None
    return None


def _candidate_dict(person: SubstratePerson) -> dict[str, Any]:
    note = _extract_review_note(person)
    sug = _canonical_suggestion_payload(person)
    review_lines = format_candidate_review_lines(person.canonical_review_reasons_json)
    defer_msg = first_candidate_review_line(person.canonical_review_reasons_json)
    row: dict[str, Any] = {
        "id": int(person.id),  # type: ignore[arg-type]
        "project_id": int(person.project_id),
        "suggested_name": str(person.name),
        "suggested_type": person.person_type or "",
        "suggested_title": (person.title or "").strip() or None,
        "suggested_affiliation": (person.affiliation or "").strip() or None,
        "suggested_public_figure": bool(person.public_figure),
        "created_at": (
            person.created_at.isoformat() if isinstance(person.created_at, datetime) else None
        ),
        "note": note,
        "status": (
            "deferred" if str(person.canonical_link_status) == CANONICAL_LINK_WAIVED else "open"
        ),
    }
    if review_lines:
        row["canonical_review_lines"] = review_lines
    if defer_msg is not None:
        row["defer_display_message"] = defer_msg
    if sug is not None:
        row["canonical_suggestion"] = sug
    return row


def _list_open_candidates(
    session: Session,
    *,
    project_id: int,
    limit: int,
    offset: int,
    needs_review: bool | None,
    q: str | None,
    type_filter: str | None,
) -> PaginatedCandidatesResponse:
    filters = _open_candidate_filters(
        project_id,
        needs_review=needs_review,
        q=q,
        type_filter=type_filter,
    )
    count_stmt = select(func.count()).select_from(SubstratePerson).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstratePerson)
        .where(*filters)
        .order_by(_substrate_list_sort_key().asc(), col(SubstratePerson.id).asc())
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


def _list_deferred_candidates(
    session: Session,
    *,
    project_id: int,
    limit: int,
    offset: int,
    q: str | None,
    type_filter: str | None,
) -> PaginatedCandidatesResponse:
    filters = _deferred_candidate_filters(project_id, q=q, type_filter=type_filter)
    count_stmt = select(func.count()).select_from(SubstratePerson).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstratePerson)
        .where(*filters)
        .order_by(_substrate_list_sort_key().asc(), col(SubstratePerson.id).asc())
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
    stylebook_slug: StylebookSlugQuery = None,
    status: str = Query("open"),
    q: str | None = Query(None),
    type_filter: str | None = Query(None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    needs_review: bool | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    if status not in ("open", "deferred", "all"):
        raise HTTPException(
            status_code=400,
            detail="Only status=open, deferred, or all is supported",
        )
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj, stylebook_slug)
    if status == "all":
        raise HTTPException(status_code=400, detail="status=all is not implemented for this queue")
    if status == "deferred":
        return _list_deferred_candidates(
            session,
            project_id=int(proj.id),
            limit=limit,
            offset=offset,
            q=q,
            type_filter=type_filter,
        )
    return _list_open_candidates(
        session,
        project_id=int(proj.id),
        limit=limit,
        offset=offset,
        needs_review=needs_review,
        q=q,
        type_filter=type_filter,
    )


@router.get("/candidates/types", response_model=dict[str, list[str]])
def candidates_types(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj, stylebook_slug)
    rows = session.exec(
        select(func.distinct(SubstratePerson.person_type)).where(
            SubstratePerson.project_id == int(proj.id),
            col(SubstratePerson.stylebook_person_canonical_id).is_(None),
            SubstratePerson.canonical_link_status.in_(
                [CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED]
            ),
            col(SubstratePerson.person_type).is_not(None),
            func.length(func.trim(col(SubstratePerson.person_type))) > 0,
        )
    ).all()
    types = sorted({str(r).strip() for r in rows if r is not None and str(r).strip()})
    return {"types": types}


def _first_occurrence_text_by_mention_id(
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
        txt = (occ.quote_text or occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


@router.get(
    "/candidates/{substrate_person_id}/context",
    response_model=CandidateContextResponse,
)
def candidate_context(
    substrate_person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    limit: int = Query(3, ge=1, le=10),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateContextResponse:
    """Small textual examples showing where this person appears in articles (lean payload)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    if person.stylebook_person_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Person is already linked to a canonical")
    if str(person.canonical_link_status) not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(status_code=409, detail="Person is not in the review queue")

    pairs = list(
        session.exec(
            select(SubstratePersonMention, SubstrateArticle)
            .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
            .where(
                SubstratePersonMention.person_id == int(substrate_person_id),
                SubstratePersonMention.deleted == False,  # noqa: E712
                SubstrateArticle.project_id == int(proj.id),
                SubstrateArticle.deleted == False,  # noqa: E712
            )
            .order_by(col(SubstratePersonMention.updated_at).desc())
            .limit(limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _ in pairs if m.id is not None]  # type: ignore[union-attr]
    texts = _first_occurrence_text_by_mention_id(session, mention_ids)
    examples: list[CandidateContextItem] = []
    for mention, article in pairs:
        mid = int(mention.id)  # type: ignore[arg-type]
        txt = texts.get(mid) or ""
        if not txt:
            continue
        ah, au = article_fields_for_linked_mention(article)
        examples.append(
            CandidateContextItem(
                article_id=int(article.id),  # type: ignore[arg-type]
                article_headline=ah,
                article_url=au,
                text=txt,
            )
        )

    return CandidateContextResponse(
        substrate_person_id=int(substrate_person_id),
        created_at=(
            person.created_at.isoformat() if isinstance(person.created_at, datetime) else None
        ),
        note=_extract_review_note(person),
        examples=examples,
    )


@router.post("/candidates/{substrate_person_id}/note")
def candidate_update_note(
    substrate_person_id: int,
    body: UpdateCandidateNoteBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Attach a short editor note to a review queue item (stored on the person row)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    if person.stylebook_person_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Person is already linked to a canonical")
    if str(person.canonical_link_status) not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(status_code=409, detail="Person is not in the review queue")

    note = (body.note or "").strip()
    raw = person.canonical_review_reasons_json
    reasons: list[dict[str, Any]] = []
    if isinstance(raw, list):
        reasons = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        reasons = [raw]

    reasons = [r for r in reasons if str(r.get("code") or "") != "review_note"]
    if note:
        reasons.append({"code": "review_note", "note": note, "provenance": "stylebook_ui"})
    person.canonical_review_reasons_json = reasons if reasons else None
    session.add(person)
    session.commit()
    return {"message": "updated"}


class SuggestedCanonicalItem(BaseModel):
    canonical_id: str
    label: str
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None


class SuggestedCanonicalsResponse(BaseModel):
    suggestions: list[SuggestedCanonicalItem]


@router.get(
    "/candidates/{substrate_person_id}/suggested-canonicals",
    response_model=SuggestedCanonicalsResponse,
)
def candidates_suggested_canonicals(
    substrate_person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    limit: int = Query(24, ge=1, le=48),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SuggestedCanonicalsResponse:
    """Ranked canonical matches (pending candidate or linked row for relink/move)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    st = str(person.canonical_link_status or "")
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED):
        raise HTTPException(
            status_code=409,
            detail=(
                "Suggestions are only available for pending, deferred, or linked substrate people"
            ),
        )
    if (
        st in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED)
        and person.stylebook_person_canonical_id is not None
    ):
        raise HTTPException(status_code=409, detail="Invalid pending state: canonical FK is set")
    ranked = rank_canonical_suggestions_for_substrate(
        session, stylebook_id=stylebook_id, person=person, limit=limit
    )
    ids = [str(cid) for cid, _ in ranked]
    canon_by_id: dict[str, StylebookPersonCanonical] = {}
    if ids:
        canon_rows = list(
            session.exec(
                select(StylebookPersonCanonical).where(col(StylebookPersonCanonical.id).in_(ids))
            ).all()
        )
        for row in canon_rows:
            if row.id is not None:
                canon_by_id[str(row.id)] = row
    suggestions: list[SuggestedCanonicalItem] = []
    for cid, lab in ranked:
        c = canon_by_id.get(str(cid))
        pt = (str(c.person_type).strip() if c and c.person_type else "") or None
        title = (str(c.title).strip() if c and c.title else "") or None
        aff = (str(c.affiliation).strip() if c and c.affiliation else "") or None
        suggestions.append(
            SuggestedCanonicalItem(
                canonical_id=str(cid),
                label=lab,
                person_type=pt,
                title=title,
                affiliation=aff,
            )
        )
    return SuggestedCanonicalsResponse(suggestions=suggestions)


class AcceptCandidateBody(BaseModel):
    create_new: bool = False
    stylebook_person_canonical_id: UUID | None = None
    name: str | None = None
    person_type: str | None = Field(
        default=None,
        description="When create_new, optional person type for the new canonical.",
    )


class AcceptCandidateResponse(BaseModel):
    message: str
    stylebook_person_canonical_id: str


@router.post("/candidates/{substrate_person_id}/defer")
def defer_candidate(
    substrate_person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Defer canonical linking for a substrate row (remove from open queue without linking)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    if person.stylebook_person_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Person is already linked to a canonical")
    if person.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Person is not in the review queue (status must be pending)",
        )

    person.canonical_link_status = CANONICAL_LINK_WAIVED
    person.canonical_review_reasons_json = [
        {"code": "deferred_manual", "provenance": "stylebook_ui_defer"}
    ]
    session.add(person)
    session.commit()
    return {"message": "deferred"}


@router.post("/candidates/{substrate_person_id}/clear-recommendation")
def clear_candidate_recommendation(
    substrate_person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    if person.stylebook_person_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Person is already linked to a canonical")
    if person.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Person is not in the review queue (status must be pending)",
        )

    person.canonical_review_reasons_json = strip_ai_recommendations_from_review_reasons(
        person.canonical_review_reasons_json
    )
    session.add(person)
    session.commit()
    return {"message": "cleared"}


@router.post("/candidates/{substrate_person_id}/accept")
def accept_candidate(
    substrate_person_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    body: AcceptCandidateBody = Body(default_factory=AcceptCandidateBody),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AcceptCandidateResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)

    person = session.get(SubstratePerson, substrate_person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate person not found")
    if person.stylebook_person_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Person already linked to a canonical")
    if person.canonical_link_status not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(
            status_code=400,
            detail=(
                "Person is not in the canonical review queue (status must be pending or deferred)"
            ),
        )

    if body.create_new:
        label = (body.name or person.name or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="name is required when create_new is true")
        if body.person_type is not None:
            pt = (body.person_type or "").strip() or None
            person.person_type = pt
            session.add(person)
            session.flush()
        materialize_new_canonical_and_link(
            session,
            stylebook_id=stylebook_id,
            person=person,
            label=label,
            provenance="stylebook_ui_accept",
        )
        cid = str(person.stylebook_person_canonical_id or "")
        if not cid:
            raise HTTPException(status_code=500, detail="Canonical could not be created")
        person.canonical_review_reasons_json = [
            {"code": "linked_manual_accept_create_new", "canonical_id": cid}
        ]
        session.add(person)
        if body.person_type is not None:
            canon = session.get(StylebookPersonCanonical, cid)
            if canon is not None:
                canon.person_type = person.person_type
                session.add(canon)
    else:
        if body.stylebook_person_canonical_id is None:
            raise HTTPException(
                status_code=400,
                detail="stylebook_person_canonical_id is required when create_new is false",
            )
        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            person=person,
            target_canonical_id=str(body.stylebook_person_canonical_id),
            provenance="stylebook_ui_accept",
        )
        refresh_aliases_for_linked_person(
            session,
            stylebook_id=stylebook_id,
            person=person,
            provenance="stylebook_ui_accept",
        )
        person.canonical_review_reasons_json = [
            {
                "code": "linked_manual_accept_existing",
                "canonical_id": str(body.stylebook_person_canonical_id),
            }
        ]
        session.add(person)
        cid = str(body.stylebook_person_canonical_id)

    session.commit()
    return AcceptCandidateResponse(
        message="linked",
        stylebook_person_canonical_id=cid,
    )
