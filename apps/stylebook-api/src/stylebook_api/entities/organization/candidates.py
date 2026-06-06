"""Organization candidate queue: substrate rows not yet linked to a Stylebook canonical."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    StylebookOrganizationCanonical,
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.entities.organization.persist import (
    link_substrate_to_canonical_atomic,
    materialize_new_canonical_and_link,
    rank_canonical_suggestions_for_substrate,
    refresh_aliases_for_linked_organization,
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

router = APIRouter(prefix="/v1/organizations", tags=["organization-candidates"])


def _substrate_list_sort_key():
    return func.lower(col(SubstrateOrganization.normalized_name))


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
    substrate_organization_id: int
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
        SubstrateOrganization.project_id == project_id,
        col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
        SubstrateOrganization.canonical_link_status == CANONICAL_LINK_PENDING,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstrateOrganization.name).ilike(term),
                col(SubstrateOrganization.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstrateOrganization.organization_type == tf)
    if needs_review is True:
        filters.append(
            exists().where(
                SubstrateOrganizationMention.organization_id == SubstrateOrganization.id,
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
                SubstrateOrganizationMention.needs_review == True,  # noqa: E712
            )
        )
    return filters


def _deferred_candidate_filters(
    project_id: int, *, q: str | None, type_filter: str | None
) -> list[Any]:
    filters: list[Any] = [
        SubstrateOrganization.project_id == project_id,
        col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
        SubstrateOrganization.canonical_link_status == CANONICAL_LINK_WAIVED,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstrateOrganization.name).ilike(term),
                col(SubstrateOrganization.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstrateOrganization.organization_type == tf)
    return filters


def _canonical_suggestion_payload(organization: SubstrateOrganization) -> dict[str, Any] | None:
    """Merge rules-plan + adjudication blobs for Stylebook UI (ingest recommendations)."""
    raw = organization.canonical_review_reasons_json
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
        cid = sug.get("stylebook_organization_canonical_id")
        out["stylebook_organization_canonical_id"] = str(cid) if cid is not None else None
        out["source"] = sug.get("source")
    if adj is not None:
        out["adjudication_confidence"] = adj.get("confidence")
        out["adjudication_rationale"] = adj.get("rationale")
        out["adjudication_model"] = adj.get("model")
        out["adjudication_outcome"] = adj.get("outcome")
        if (
            out.get("stylebook_organization_canonical_id") is None
            and adj.get("canonical_id") is not None
        ):
            raw_c = adj.get("canonical_id")
            if raw_c is not None:
                out["stylebook_organization_canonical_id"] = str(raw_c).strip() or None
    return out or None


def _extract_review_note(organization: SubstrateOrganization) -> str | None:
    raw = organization.canonical_review_reasons_json
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


def _candidate_dict(organization: SubstrateOrganization) -> dict[str, Any]:
    note = _extract_review_note(organization)
    sug = _canonical_suggestion_payload(organization)
    review_lines = format_candidate_review_lines(organization.canonical_review_reasons_json)
    defer_msg = first_candidate_review_line(organization.canonical_review_reasons_json)
    row: dict[str, Any] = {
        "id": int(organization.id),  # type: ignore[arg-type]
        "project_id": int(organization.project_id),
        "suggested_name": str(organization.name),
        "suggested_type": organization.organization_type or "",
        "created_at": (
            organization.created_at.isoformat()
            if isinstance(organization.created_at, datetime)
            else None
        ),
        "note": note,
        "status": (
            "deferred"
            if str(organization.canonical_link_status) == CANONICAL_LINK_WAIVED
            else "open"
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
    count_stmt = select(func.count()).select_from(SubstrateOrganization).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstrateOrganization)
        .where(*filters)
        .order_by(_substrate_list_sort_key().asc(), col(SubstrateOrganization.id).asc())
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
    count_stmt = select(func.count()).select_from(SubstrateOrganization).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstrateOrganization)
        .where(*filters)
        .order_by(_substrate_list_sort_key().asc(), col(SubstrateOrganization.id).asc())
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
        select(func.distinct(SubstrateOrganization.organization_type)).where(
            SubstrateOrganization.project_id == int(proj.id),
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
            SubstrateOrganization.canonical_link_status.in_(
                [CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED]
            ),
            col(SubstrateOrganization.organization_type).is_not(None),
            func.length(func.trim(col(SubstrateOrganization.organization_type))) > 0,
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
        txt = (occ.quote_text or occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


@router.get(
    "/candidates/{substrate_organization_id}/context",
    response_model=CandidateContextResponse,
)
def candidate_context(
    substrate_organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    limit: int = Query(3, ge=1, le=10),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateContextResponse:
    """Small textual examples showing where this organization appears in articles."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    organization = session.get(SubstrateOrganization, substrate_organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate organization not found")
    if organization.stylebook_organization_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Organization is already linked to a canonical")
    if str(organization.canonical_link_status) not in (
        CANONICAL_LINK_PENDING,
        CANONICAL_LINK_WAIVED,
    ):
        raise HTTPException(status_code=409, detail="Organization is not in the review queue")

    pairs = list(
        session.exec(
            select(SubstrateOrganizationMention, SubstrateArticle)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
            .where(
                SubstrateOrganizationMention.organization_id == int(substrate_organization_id),
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
                SubstrateArticle.project_id == int(proj.id),
                SubstrateArticle.deleted == False,  # noqa: E712
            )
            .order_by(col(SubstrateOrganizationMention.updated_at).desc())
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
        substrate_organization_id=int(substrate_organization_id),
        created_at=(
            organization.created_at.isoformat()
            if isinstance(organization.created_at, datetime)
            else None
        ),
        note=_extract_review_note(organization),
        examples=examples,
    )


@router.post("/candidates/{substrate_organization_id}/note")
def candidate_update_note(
    substrate_organization_id: int,
    body: UpdateCandidateNoteBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Attach a short editor note to a review queue item (stored on the organization row)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    organization = session.get(SubstrateOrganization, substrate_organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate organization not found")
    if organization.stylebook_organization_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Organization is already linked to a canonical")
    if str(organization.canonical_link_status) not in (
        CANONICAL_LINK_PENDING,
        CANONICAL_LINK_WAIVED,
    ):
        raise HTTPException(status_code=409, detail="Organization is not in the review queue")

    note = (body.note or "").strip()
    raw = organization.canonical_review_reasons_json
    reasons: list[dict[str, Any]] = []
    if isinstance(raw, list):
        reasons = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        reasons = [raw]

    reasons = [r for r in reasons if str(r.get("code") or "") != "review_note"]
    if note:
        reasons.append({"code": "review_note", "note": note, "provenance": "stylebook_ui"})
    organization.canonical_review_reasons_json = reasons if reasons else None
    session.add(organization)
    session.commit()
    return {"message": "updated"}


class SuggestedCanonicalItem(BaseModel):
    canonical_id: str
    label: str
    organization_type: str | None = None


class SuggestedCanonicalsResponse(BaseModel):
    suggestions: list[SuggestedCanonicalItem]


@router.get(
    "/candidates/{substrate_organization_id}/suggested-canonicals",
    response_model=SuggestedCanonicalsResponse,
)
def candidates_suggested_canonicals(
    substrate_organization_id: int,
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
    organization = session.get(SubstrateOrganization, substrate_organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate organization not found")
    st = str(organization.canonical_link_status or "")
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED):
        raise HTTPException(
            status_code=409,
            detail=(
                "Suggestions are only available for pending, deferred, or linked "
                "substrate organizations"
            ),
        )
    if (
        st in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED)
        and organization.stylebook_organization_canonical_id is not None
    ):
        raise HTTPException(status_code=409, detail="Invalid pending state: canonical FK is set")
    ranked = rank_canonical_suggestions_for_substrate(
        session, stylebook_id=stylebook_id, organization=organization, limit=limit
    )
    ids = [str(cid) for cid, _ in ranked]
    canon_by_id: dict[str, StylebookOrganizationCanonical] = {}
    if ids:
        canon_rows = list(
            session.exec(
                select(StylebookOrganizationCanonical).where(
                    col(StylebookOrganizationCanonical.id).in_(ids)
                )
            ).all()
        )
        for row in canon_rows:
            if row.id is not None:
                canon_by_id[str(row.id)] = row
    suggestions: list[SuggestedCanonicalItem] = []
    for cid, lab in ranked:
        c = canon_by_id.get(str(cid))
        ot = (str(c.organization_type).strip() if c and c.organization_type else "") or None
        suggestions.append(
            SuggestedCanonicalItem(
                canonical_id=str(cid),
                label=lab,
                organization_type=ot,
            )
        )
    return SuggestedCanonicalsResponse(suggestions=suggestions)


class AcceptCandidateBody(BaseModel):
    create_new: bool = False
    stylebook_organization_canonical_id: UUID | None = None
    name: str | None = None
    organization_type: str | None = Field(
        default=None,
        description="When create_new, optional organization type for the new canonical.",
    )


class AcceptCandidateResponse(BaseModel):
    message: str
    stylebook_organization_canonical_id: str


@router.post("/candidates/{substrate_organization_id}/defer")
def defer_candidate(
    substrate_organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Defer canonical linking for a substrate row (remove from open queue without linking)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

    organization = session.get(SubstrateOrganization, substrate_organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate organization not found")
    if organization.stylebook_organization_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Organization is already linked to a canonical")
    if organization.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Organization is not in the review queue (status must be pending)",
        )

    organization.canonical_link_status = CANONICAL_LINK_WAIVED
    organization.canonical_review_reasons_json = [
        {"code": "deferred_manual", "provenance": "stylebook_ui_defer"}
    ]
    session.add(organization)
    session.commit()
    return {"message": "deferred"}


@router.post("/candidates/{substrate_organization_id}/accept")
def accept_candidate(
    substrate_organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    body: AcceptCandidateBody = Body(default_factory=AcceptCandidateBody),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AcceptCandidateResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)

    organization = session.get(SubstrateOrganization, substrate_organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate organization not found")
    if organization.stylebook_organization_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Organization already linked to a canonical")
    if organization.canonical_link_status not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(
            status_code=400,
            detail=(
                "Organization is not in the canonical review queue "
                "(status must be pending or deferred)"
            ),
        )

    if body.create_new:
        label = (body.name or organization.name or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="name is required when create_new is true")
        if body.organization_type is not None:
            ot = (body.organization_type or "").strip() or None
            organization.organization_type = ot
            session.add(organization)
            session.flush()
        materialize_new_canonical_and_link(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            label=label,
            provenance="stylebook_ui_accept",
        )
        cid = str(organization.stylebook_organization_canonical_id or "")
        if not cid:
            raise HTTPException(status_code=500, detail="Canonical could not be created")
        organization.canonical_review_reasons_json = [
            {"code": "linked_manual_accept_create_new", "canonical_id": cid}
        ]
        session.add(organization)
        if body.organization_type is not None:
            canon = session.get(StylebookOrganizationCanonical, cid)
            if canon is not None:
                canon.organization_type = organization.organization_type
                session.add(canon)
    else:
        if body.stylebook_organization_canonical_id is None:
            raise HTTPException(
                status_code=400,
                detail="stylebook_organization_canonical_id is required when create_new is false",
            )
        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            target_canonical_id=str(body.stylebook_organization_canonical_id),
            provenance="stylebook_ui_accept",
        )
        refresh_aliases_for_linked_organization(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            provenance="stylebook_ui_accept",
        )
        organization.canonical_review_reasons_json = [
            {
                "code": "linked_manual_accept_existing",
                "canonical_id": str(body.stylebook_organization_canonical_id),
            }
        ]
        session.add(organization)
        cid = str(body.stylebook_organization_canonical_id)

    session.commit()
    return AcceptCandidateResponse(
        message="linked",
        stylebook_organization_canonical_id=cid,
    )
