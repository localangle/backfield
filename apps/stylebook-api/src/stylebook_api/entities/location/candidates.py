"""Location candidate queue: substrate rows not yet linked to a Stylebook canonical."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_entities.canonical.candidate_review import (
    strip_ai_recommendations_from_review_reasons,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.catalog.search import substrate_name_ilike_filter
from backfield_entities.cleanup.decision_ops import (
    CandidateDecisionError,
    create_candidate_canonical,
    link_candidate,
)
from backfield_entities.cleanup.decision_ops import defer_candidate as defer_candidate_decision
from backfield_entities.cleanup.entity_models import cleanup_entity_models
from backfield_entities.entities.linking.substrate_actions import (
    rank_canonical_suggestions_for_substrate,
)
from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.candidate_decision_errors import candidate_decision_http_error
from stylebook_api.helpers.candidate_review_display import (
    first_candidate_review_line,
    format_candidate_review_lines,
)
from stylebook_api.helpers.candidate_scope import require_candidate_project_in_stylebook
from stylebook_api.helpers.project_scope import (
    project_by_slug as _project_by_slug,
)
from stylebook_api.helpers.project_scope import (
    require_stylebook_id as _require_stylebook_id,
)
from stylebook_api.mention_serialization import article_fields_for_linked_mention

router = APIRouter(prefix="/v1", tags=["location-candidates"])


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


def open_candidate_filters(
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
        filters.append(
            substrate_name_ilike_filter(
                q,
                name_column=col(SubstrateLocation.name),
                normalized_name_column=col(SubstrateLocation.normalized_name),
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


def deferred_candidate_filters(
    project_id: int, *, q: str | None, type_filter: str | None
) -> list[Any]:
    filters: list[Any] = [
        SubstrateLocation.project_id == project_id,
        col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
        SubstrateLocation.canonical_link_status == CANONICAL_LINK_WAIVED,
    ]
    if q:
        filters.append(
            substrate_name_ilike_filter(
                q,
                name_column=col(SubstrateLocation.name),
                normalized_name_column=col(SubstrateLocation.normalized_name),
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
        out["stylebook_location_canonical_id"] = str(cid) if cid is not None else None
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
            raw_c = adj.get("canonical_id")
            if raw_c is not None:
                out["stylebook_location_canonical_id"] = str(raw_c).strip() or None
        if out.get("suggested_action") is None:
            outcome = str(adj.get("outcome") or "").strip()
            if outcome == "link_existing" and out.get("stylebook_location_canonical_id"):
                out["suggested_action"] = "link_existing"
            elif outcome == "no_high_confidence_link":
                out["suggested_action"] = "materialize_new"
    return out or None


def serialize_candidate(loc: SubstrateLocation) -> dict[str, Any]:
    note = _extract_review_note(loc)
    sug = _canonical_suggestion_payload(loc)
    review_lines = format_candidate_review_lines(loc.canonical_review_reasons_json)
    defer_msg = first_candidate_review_line(loc.canonical_review_reasons_json)
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
    if review_lines:
        row["canonical_review_lines"] = review_lines
    if defer_msg is not None:
        row["defer_display_message"] = defer_msg
    if sug is not None:
        row["canonical_suggestion"] = sug
    return row


def _candidate_dict_with_project(
    loc: SubstrateLocation, project: BackfieldProject
) -> dict[str, Any]:
    row = serialize_candidate(loc)
    row.update(project_slug=project.slug, project_name=project.name)
    return row


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
    filters = open_candidate_filters(
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
    project = session.get(BackfieldProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    candidates = [_candidate_dict_with_project(r, project) for r in rows]
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
    filters = deferred_candidate_filters(project_id, q=q, type_filter=type_filter)
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
    project = session.get(BackfieldProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    candidates = [_candidate_dict_with_project(r, project) for r in rows]
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


@router.get("/candidates/ungrouped", response_model=PaginatedCandidatesResponse)
def candidates_ungrouped(
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


@router.get("/candidates/clusters", response_model=PaginatedClustersResponse)
def candidates_clusters(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    status: str = Query("open"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedClustersResponse:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj, stylebook_slug)
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
    stylebook_slug: StylebookSlugQuery = None,
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _require_stylebook_id(session, proj, stylebook_slug)
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
    stylebook_slug: StylebookSlugQuery = None,
    limit: int = Query(3, ge=1, le=10),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateContextResponse:
    """Small textual examples showing where this location appears in articles (lean payload)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    _ = _require_stylebook_id(session, proj, stylebook_slug)

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
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Attach a short editor note to a review queue item (stored on the location row)."""
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Substrate location not found")
    require_candidate_project_in_stylebook(
        session,
        auth=auth,
        project_id=int(loc.project_id),
        project_slug=project_slug,
        stylebook_slug=stylebook_slug,
        require_edit=True,
    )
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
    canonical_id: str
    label: str
    location_type: str | None = None
    formatted_address: str | None = None


class SuggestedCanonicalsResponse(BaseModel):
    suggestions: list[SuggestedCanonicalItem]


@router.get(
    "/candidates/{substrate_location_id}/suggested-canonicals",
    response_model=SuggestedCanonicalsResponse,
)
def candidates_suggested_canonicals(
    substrate_location_id: int,
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
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Substrate location not found")
    st = str(loc.canonical_link_status or "")
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED):
        raise HTTPException(
            status_code=409,
            detail=(
                "Suggestions are only available for pending, deferred, or linked "
                "substrate locations"
            ),
        )
    if (
        st in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED)
        and loc.stylebook_location_canonical_id is not None
    ):
        raise HTTPException(status_code=409, detail="Invalid pending state: canonical FK is set")
    ranked = rank_canonical_suggestions_for_substrate(
        session, stylebook_id=stylebook_id, location=loc, limit=limit
    )
    ids = [str(cid) for cid, _ in ranked]
    canon_by_id: dict[str, StylebookLocationCanonical] = {}
    if ids:
        canon_rows = list(
            session.exec(
                select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(ids))
            ).all()
        )
        for row in canon_rows:
            if row.id is not None:
                canon_by_id[str(row.id)] = row
    suggestions: list[SuggestedCanonicalItem] = []
    for cid, lab in ranked:
        c = canon_by_id.get(str(cid))
        lt = (str(c.location_type).strip() if c and c.location_type else "") or None
        fa = (str(c.formatted_address).strip() if c and c.formatted_address else "") or None
        suggestions.append(
            SuggestedCanonicalItem(
                canonical_id=str(cid),
                label=lab,
                location_type=lt,
                formatted_address=fa,
            )
        )
    return SuggestedCanonicalsResponse(suggestions=suggestions)


class AcceptCandidateBody(BaseModel):
    create_new: bool = False
    stylebook_location_id: UUID | None = None
    name: str | None = None
    geometry_json: dict[str, Any] | None = None
    location_type: str | None = Field(
        default=None,
        description="When create_new, optional PlaceExtract type for the new canonical.",
    )


class AcceptCandidateResponse(BaseModel):
    message: str
    stylebook_location_canonical_id: str


@router.post("/candidates/{substrate_location_id}/defer")
def defer_candidate(
    substrate_location_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    """Defer canonical linking for a substrate row (remove from open queue without linking)."""
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Substrate location not found")
    require_candidate_project_in_stylebook(
        session,
        auth=auth,
        project_id=int(loc.project_id),
        project_slug=project_slug,
        stylebook_slug=stylebook_slug,
        require_edit=True,
    )
    try:
        defer_candidate_decision(
            session, cleanup_entity_models("locations"), loc, provenance="stylebook_ui_defer"
        )
    except CandidateDecisionError as exc:
        raise candidate_decision_http_error(exc, not_in_queue_status=409) from exc
    session.commit()
    return {"message": "deferred"}


@router.post("/candidates/{substrate_location_id}/clear-recommendation")
def clear_candidate_recommendation(
    substrate_location_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Substrate location not found")
    require_candidate_project_in_stylebook(
        session,
        auth=auth,
        project_id=int(loc.project_id),
        project_slug=project_slug,
        stylebook_slug=stylebook_slug,
        require_edit=True,
    )
    if loc.stylebook_location_canonical_id is not None:
        raise HTTPException(status_code=409, detail="Location is already linked to a canonical")
    if loc.canonical_link_status != CANONICAL_LINK_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Location is not in the review queue (status must be pending)",
        )

    loc.canonical_review_reasons_json = strip_ai_recommendations_from_review_reasons(
        loc.canonical_review_reasons_json
    )
    session.add(loc)
    session.commit()
    return {"message": "cleared"}


@router.post("/candidates/{substrate_location_id}/accept")
def accept_candidate(
    substrate_location_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    body: AcceptCandidateBody = Body(default_factory=AcceptCandidateBody),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AcceptCandidateResponse:
    loc = session.get(SubstrateLocation, substrate_location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Substrate location not found")
    _, guarded_stylebook = require_candidate_project_in_stylebook(
        session,
        auth=auth,
        project_id=int(loc.project_id),
        project_slug=project_slug,
        stylebook_slug=stylebook_slug,
        require_edit=True,
    )
    stylebook_id = int(guarded_stylebook.id)
    models = cleanup_entity_models("locations")
    try:
        if body.create_new:
            canonical_id = create_candidate_canonical(
                session,
                models,
                loc,
                stylebook_id=stylebook_id,
                name=body.name,
                kind=body.location_type,
                geometry_json=body.geometry_json,
                provenance="stylebook_ui_accept",
            )
        else:
            if body.stylebook_location_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="stylebook_location_id is required when create_new is false",
                )
            canonical_id = link_candidate(
                session,
                models,
                loc,
                stylebook_id=stylebook_id,
                canonical_id=str(body.stylebook_location_id),
                provenance="stylebook_ui_accept",
            )
    except CandidateDecisionError as exc:
        raise candidate_decision_http_error(exc, not_in_queue_status=400) from exc

    session.commit()
    return AcceptCandidateResponse(
        message="linked",
        stylebook_location_canonical_id=canonical_id,
    )
