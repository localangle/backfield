"""Location candidate queue: substrate rows not yet linked to a Stylebook canonical."""

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
from backfield_stylebook.canonical_link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_stylebook.locations import refresh_aliases_for_linked_location
from backfield_stylebook.place_extract_location_types import PLACE_EXTRACT_LOCATION_TYPES
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from backfield_stylebook.substrate_canonical_link_actions import (
    rank_canonical_suggestions_for_substrate,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import exists, or_
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.mention_serialization import article_fields_for_linked_mention

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


class CandidateContextItem(BaseModel):
    article_id: int
    article_headline: str | None = None
    article_url: str | None = None
    text: str


class CandidateContextResponse(BaseModel):
    substrate_location_id: int
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
        SubstrateLocation.project_id == project_id,
        col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
        SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstrateLocation.name).ilike(term),
                col(SubstrateLocation.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstrateLocation.location_type == tf)
    if needs_review is True:
        filters.append(
            exists().where(
                SubstrateLocationMention.location_id == SubstrateLocation.id,
                SubstrateLocationMention.deleted == False,  # noqa: E712
                SubstrateLocationMention.needs_review == True,  # noqa: E712
            )
        )
    return filters


def _deferred_candidate_filters(
    project_id: int, *, q: str | None, type_filter: str | None
) -> list[Any]:
    filters: list[Any] = [
        SubstrateLocation.project_id == project_id,
        col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
        SubstrateLocation.canonical_link_status == CANONICAL_LINK_WAIVED,
    ]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                col(SubstrateLocation.name).ilike(term),
                col(SubstrateLocation.normalized_name).ilike(term),
            )
        )
    if type_filter:
        tf = type_filter.strip()
        if tf:
            filters.append(SubstrateLocation.location_type == tf)
    return filters


def _canonical_suggestion_payload(loc: SubstrateLocation) -> dict[str, Any] | None:
    """Merge rules-plan + adjudication blobs for Stylebook UI (ingest recommendations)."""
    raw = loc.canonical_review_reasons_json
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
        cid = sug.get("stylebook_location_canonical_id")
        out["stylebook_location_canonical_id"] = int(cid) if cid is not None else None
        out["source"] = sug.get("source")
    if adj is not None:
        out["adjudication_confidence"] = adj.get("confidence")
        out["adjudication_rationale"] = adj.get("rationale")
        out["adjudication_model"] = adj.get("model")
        out["adjudication_outcome"] = adj.get("outcome")
        if (
            out.get("stylebook_location_canonical_id") is None
            and adj.get("canonical_id") is not None
        ):
            try:
                out["stylebook_location_canonical_id"] = int(adj["canonical_id"])
            except (TypeError, ValueError):
                pass
    return out or None


def _candidate_dict(loc: SubstrateLocation) -> dict[str, Any]:
    note = _extract_review_note(loc)
    sug = _canonical_suggestion_payload(loc)
    defer_msg = _extract_defer_display_message(loc)
    row: dict[str, Any] = {
        "id": int(loc.id),  # type: ignore[arg-type]
        "project_id": int(loc.project_id),
        "suggested_name": str(loc.name),
        "suggested_type": loc.location_type or "",
        "suggested_formatted_address": loc.formatted_address,
        "created_at": loc.created_at.isoformat() if isinstance(loc.created_at, datetime) else None,
        "note": note,
        "status": (
            "deferred" if str(loc.canonical_link_status) == CANONICAL_LINK_WAIVED else "open"
        ),
    }
    if defer_msg is not None:
        row["defer_display_message"] = defer_msg
    if sug is not None:
        row["canonical_suggestion"] = sug
    return row


def _extract_defer_display_message(loc: SubstrateLocation) -> str | None:
    """Short message from ingest/policy reasons (e.g. ``private_place_or_residence``) for UI."""
    raw = loc.canonical_review_reasons_json
    if raw is None:
        return None
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        items = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        items = [raw]
    skip_codes = frozenset(
        {
            "canonical_suggestion",
            "canonical_adjudication",
            "review_note",
            "deferred_manual",
        }
    )
    for it in items:
        code = str(it.get("code") or "")
        if code in skip_codes:
            continue
        msg = it.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return None


def _extract_review_note(loc: SubstrateLocation) -> str | None:
    raw = loc.canonical_review_reasons_json
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
    count_stmt = select(func.count()).select_from(SubstrateLocation).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstrateLocation)
        .where(*filters)
        .order_by(col(SubstrateLocation.normalized_name).asc(), col(SubstrateLocation.id).asc())
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
    count_stmt = select(func.count()).select_from(SubstrateLocation).where(*filters)
    total = int(session.scalar(count_stmt) or 0)
    stmt = (
        select(SubstrateLocation)
        .where(*filters)
        .order_by(col(SubstrateLocation.normalized_name).asc(), col(SubstrateLocation.id).asc())
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
    _require_stylebook_id(session, proj)
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


@router.get("/candidates/ungrouped", response_model=PaginatedCandidatesResponse)
def candidates_ungrouped(
    project_slug: str = Query(...),
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
    _require_stylebook_id(session, proj)
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
    # Fixed taxonomy from PlaceExtract (not DISTINCT from queue — empty queue had no types).
    return {"types": list(PLACE_EXTRACT_LOCATION_TYPES)}


def _first_occurrence_text_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, str]:
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
        # Prefer quote_text if present; fallback to mention_text.
        txt = (occ.quote_text or occ.mention_text or "").strip()
        if txt:
            out[mid] = txt
    return out


@router.get(
    "/candidates/{substrate_location_id}/context",
    response_model=CandidateContextResponse,
)
def candidate_context(
    substrate_location_id: int,
    project_slug: str = Query(...),
    limit: int = Query(3, ge=1, le=10),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateContextResponse:
    """Small textual examples showing where this location appears in articles (lean payload)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj)

    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    if loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Location is already linked to a canonical")
    if str(loc.canonical_link_status) not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(status_code=409, detail="Location is not in the review queue")

    pairs = list(
        session.exec(
            select(SubstrateLocationMention, SubstrateArticle)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .where(
                SubstrateLocationMention.location_id == int(substrate_location_id),
                SubstrateLocationMention.deleted == False,  # noqa: E712
                SubstrateArticle.project_id == int(proj.id),
                SubstrateArticle.deleted == False,  # noqa: E712
            )
            .order_by(col(SubstrateLocationMention.updated_at).desc())
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
        substrate_location_id=int(substrate_location_id),
        created_at=loc.created_at.isoformat() if isinstance(loc.created_at, datetime) else None,
        note=_extract_review_note(loc),
        examples=examples,
    )


@router.post("/candidates/{substrate_location_id}/note")
def candidate_update_note(
    substrate_location_id: int,
    body: UpdateCandidateNoteBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Attach a short editor note to a review queue item (stored on the location row)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj)

    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    if loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Location is already linked to a canonical")
    if str(loc.canonical_link_status) not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        raise HTTPException(status_code=409, detail="Location is not in the review queue")

    note = (body.note or "").strip()
    raw = loc.canonical_review_reasons_json
    reasons: list[dict[str, Any]] = []
    if isinstance(raw, list):
        reasons = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        reasons = [raw]

    # Remove any existing note entries.
    reasons = [r for r in reasons if str(r.get("code") or "") != "review_note"]
    if note:
        reasons.append({"code": "review_note", "note": note, "provenance": "stylebook_ui"})
    loc.canonical_review_reasons_json = reasons if reasons else None
    session.add(loc)
    session.commit()
    return {"message": "updated"}


class SuggestedCanonicalItem(BaseModel):
    canonical_id: int
    label: str


class SuggestedCanonicalsResponse(BaseModel):
    suggestions: list[SuggestedCanonicalItem]


@router.get(
    "/candidates/{substrate_location_id}/suggested-canonicals",
    response_model=SuggestedCanonicalsResponse,
)
def candidates_suggested_canonicals(
    substrate_location_id: int,
    project_slug: str = Query(...),
    limit: int = Query(24, ge=1, le=48),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SuggestedCanonicalsResponse:
    """Ranked canonical matches (pending candidate or linked row for relink/move)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj)
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    st = str(loc.canonical_link_status or "")
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED):
        raise HTTPException(
            status_code=409,
            detail="Suggestions are only available for pending or linked substrate locations",
        )
    if st == CANONICAL_LINK_PENDING and loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Invalid pending state: canonical FK is set")
    ranked = rank_canonical_suggestions_for_substrate(
        session, stylebook_id=stylebook_id, location=loc, limit=limit
    )
    return SuggestedCanonicalsResponse(
        suggestions=[SuggestedCanonicalItem(canonical_id=cid, label=lab) for cid, lab in ranked]
    )


class AcceptCandidateBody(BaseModel):
    create_new: bool = False
    stylebook_location_id: int | None = None
    name: str | None = None
    geometry_json: dict[str, Any] | None = None


class AcceptCandidateResponse(BaseModel):
    message: str
    stylebook_location_canonical_id: int


@router.post("/candidates/{substrate_location_id}/defer")
def defer_candidate(
    substrate_location_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Defer canonical linking for a substrate row (remove from open queue without linking)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj)

    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    if loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Location is already linked to a canonical")
    if loc.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Location is not in the review queue (status must be pending)",
        )

    loc.canonical_link_status = CANONICAL_LINK_WAIVED
    loc.canonical_review_reasons_json = [
        {"code": "deferred_manual", "provenance": "stylebook_ui_defer"}
    ]
    session.add(loc)
    session.commit()
    return {"message": "deferred"}


@router.post("/candidates/{substrate_location_id}/accept")
def accept_candidate(
    substrate_location_id: int,
    project_slug: str = Query(...),
    body: AcceptCandidateBody = Body(default_factory=AcceptCandidateBody),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AcceptCandidateResponse:
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
        lt = (loc.location_type or "").strip().lower() or None
        fa = (loc.formatted_address or "").strip() or None
        canon = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label=label,
            location_type=lt,
            formatted_address=fa,
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
    return AcceptCandidateResponse(
        message="linked",
        stylebook_location_canonical_id=int(canon.id),  # type: ignore[arg-type]
    )
