"""Project-scoped substrate locations (Stylebook UI compatibility, ``project_slug``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_db.text_sanitize import strip_nul_bytes
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.linking.substrate_actions import (
    finalize_substrate_after_article_scoped_remove,
    link_substrate_to_canonical_atomic,
    requeue_substrate_after_story_remove,
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES
from backfield_entities.ingest.semantic_indexing.reindex import (
    location_patch_affects_semantic_index,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id
from stylebook_api.mention_occurrences import replace_mention_occurrences_for_article
from stylebook_api.mention_serialization import article_fields_for_linked_mention
from stylebook_api.semantic_reindex import (
    enqueue_semantic_reindex,
    enqueue_semantic_reindex_for_entity,
)

router = APIRouter(prefix="/v1", tags=["locations"])


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
    stylebook_location_canonical_id: str | None = None

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
            stylebook_location_canonical_id=str(canon_fk) if canon_fk is not None else None,
        )


class PaginatedLocationResponse(BaseModel):
    locations: list[LocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CreateLocationFromArticleEvidenceBody(BaseModel):
    """Create a saved story place and its first article evidence in one transaction."""

    article_id: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    location_type: str = Field(min_length=1)
    mention_text: str = Field(min_length=1)
    quote_text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    role_in_story: str | None = None


class CreateLocationFromArticleEvidenceResponse(BaseModel):
    location: LocationResponse
    mention_id: int
    occurrence_id: int
    anchor: str


class PatchLocationBody(BaseModel):
    name: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    status: str | None = None
    notes: str | None = None


def _enqueue_location_reindex_for_articles(
    *,
    project_id: int,
    article_ids: set[int],
) -> None:
    for aid in sorted(article_ids):
        enqueue_semantic_reindex(
            project_id=project_id,
            article_id=aid,
            entity_type="location",
        )


class PatchGeometryBody(BaseModel):
    """Set GeoJSON geometry, or null to clear the saved place pin/footprint."""

    geometry_json: dict[str, Any] | None  # required field; use explicit JSON null to clear


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
    canonical_location_id: str
    canonical_name: str
    mentions: list[LinkedMention]
    total: int
    limit: int
    offset: int


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
    stylebook_location_canonical_id: UUID


class LinkCanonicalResponse(BaseModel):
    changed: bool


@router.post("/locations/{location_id}/unlink-canonical")
def unlink_substrate_from_canonical_route(
    location_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
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
    enqueue_semantic_reindex_for_entity(
        session,
        project_id=int(proj.id),
        entity_type="location",
        entity_id=location_id,
    )
    return {"message": "unlinked"}


@router.post("/locations/{location_id}/link-canonical", response_model=LinkCanonicalResponse)
def link_substrate_to_canonical_route(
    location_id: int,
    body: LinkCanonicalBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkCanonicalResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            location=loc,
            target_canonical_id=str(body.stylebook_location_canonical_id),
            provenance="stylebook_ui_link",
        )
    except ValueError as e:
        msg = str(e)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=409, detail=msg) from e
    session.commit()
    enqueue_semantic_reindex_for_entity(
        session,
        project_id=int(proj.id),
        entity_type="location",
        entity_id=location_id,
    )
    return LinkCanonicalResponse(changed=changed)


@router.post(
    "/locations/from-article-evidence",
    response_model=CreateLocationFromArticleEvidenceResponse,
)
def create_location_from_article_evidence(
    body: CreateLocationFromArticleEvidenceBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CreateLocationFromArticleEvidenceResponse:
    """Create a saved place from a manually selected article passage."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))

    label = body.label.strip()
    location_type = body.location_type.strip()
    mention_text = strip_nul_bytes(body.mention_text.strip())
    quote_text = strip_nul_bytes(body.quote_text.strip())
    run_id = body.run_id.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label is required")
    if location_type not in PLACE_EXTRACT_LOCATION_TYPES:
        raise HTTPException(status_code=400, detail="location_type is not supported")
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

    loc = SubstrateLocation(
        project_id=int(proj.id),
        name=label,
        normalized_name=_normalize_name(label),
        location_type=location_type,
        status="active",
        canonical_link_status=CANONICAL_LINK_PENDING,
        source_kind="manual_add",
        source_details_json={
            "source": "agate_review_add_place",
            "run_id": run_id,
        },
    )
    session.add(loc)
    session.flush()
    if loc.id is None:
        raise HTTPException(status_code=500, detail="Location could not be created")
    anchor = f"user_place:{int(loc.id)}"
    loc.source_details_json = {
        "source": "agate_review_add_place",
        "run_id": run_id,
        "raw_entry_id": anchor,
    }

    mention = SubstrateLocationMention(
        article_id=int(article.id),  # type: ignore[arg-type]
        location_id=int(loc.id),
        role_in_story=body.role_in_story.strip() if body.role_in_story else None,
        added=True,
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_place", "run_id": run_id},
    )
    session.add(mention)
    session.flush()
    if mention.id is None:
        raise HTTPException(status_code=500, detail="Location mention could not be created")

    occurrence = SubstrateLocationMentionOccurrence(
        location_mention_id=int(mention.id),
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_place", "run_id": run_id},
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
    enqueue_semantic_reindex(
        project_id=int(proj.id),
        article_id=body.article_id,
        entity_type="location",
    )
    session.refresh(loc)
    session.refresh(mention)
    session.refresh(occurrence)

    mc = _mention_counts(session, [int(loc.id)])
    return CreateLocationFromArticleEvidenceResponse(
        location=LocationResponse.from_row(loc, mc.get(int(loc.id), 0)),
        mention_id=int(mention.id),
        occurrence_id=int(occurrence.id),  # type: ignore[arg-type]
        anchor=anchor,
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
    if location_patch_affects_semantic_index(body):
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=int(proj.id),
            entity_type="location",
            entity_id=location_id,
        )
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
    loc.geometry = None
    session.add(loc)
    session.commit()
    session.refresh(loc)
    mc = _mention_counts(session, [location_id])
    return LocationResponse.from_row(loc, mc.get(location_id, 0))


@router.delete("/locations/{location_id}")
def delete_location(
    location_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    article_id: int | None = Query(
        None,
        description=(
            "When set, soft-delete mentions for this article only. If no other active "
            "mentions remain on this saved place, unlink from any canonical (without "
            "re-queueing) and delete the substrate row; otherwise the catalog link is kept."
        ),
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")

    mention_filters: list[ColumnElement[bool]] = [
        SubstrateLocationMention.location_id == location_id,
        SubstrateLocationMention.deleted == False,  # noqa: E712
    ]
    if article_id is not None:
        mention_filters.append(SubstrateLocationMention.article_id == article_id)

    mentions = session.exec(select(SubstrateLocationMention).where(*mention_filters)).all()
    article_ids = {int(mention.article_id) for mention in mentions}
    for mention in mentions:
        mention.deleted = True
        session.add(mention)
    session.flush()

    remaining = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateLocationMention)
            .where(
                SubstrateLocationMention.location_id == location_id,
                SubstrateLocationMention.deleted == False,  # noqa: E712
            )
        )
        or 0
    )

    location_deleted = False
    candidates_created = 0
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    if article_id is not None:
        try:
            location_deleted, candidates_created = finalize_substrate_after_article_scoped_remove(
                session,
                location=loc,
                remaining_active_mentions=remaining,
            )
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Location still has linked mentions or references; cannot delete.",
            ) from None
    elif remaining == 0:
        if requeue_substrate_after_story_remove(
            session,
            stylebook_id=stylebook_id,
            location=loc,
            provenance="stylebook_delete",
        ):
            candidates_created = 1
        else:
            try:
                session.delete(loc)
                location_deleted = True
            except IntegrityError:
                session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="Location still has linked mentions or references; cannot delete.",
                ) from None
    session.commit()
    _enqueue_location_reindex_for_articles(
        project_id=int(proj.id),
        article_ids=article_ids,
    )
    return {
        "message": "deleted",
        "mentions_removed": len(mentions),
        "location_deleted": location_deleted,
        "candidates_created": candidates_created,
        "links_deactivated": 0,
    }


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
        canonical_location_id=str(loc.stylebook_location_canonical_id or location_id),
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


class MentionOccurrenceIn(BaseModel):
    id: int | None = None
    client_id: str | None = None
    mention_text: str = Field(min_length=1)
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool = False


class MentionOccurrenceOut(BaseModel):
    id: int
    mention_text: str
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool
    source_kind: str


class ReplaceMentionOccurrencesIn(BaseModel):
    occurrences: list[MentionOccurrenceIn] = Field(default_factory=list, max_length=50)


class ReplaceMentionOccurrencesResponse(BaseModel):
    occurrences: list[MentionOccurrenceOut]


@router.put(
    "/locations/{location_id}/mention-occurrences",
    response_model=ReplaceMentionOccurrencesResponse,
)
def replace_location_mention_occurrences(
    location_id: int,
    body: ReplaceMentionOccurrencesIn,
    project_slug: str = Query(...),
    article_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ReplaceMentionOccurrencesResponse:
    """Replace all active mention occurrences for one article+location (Agate Review)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc = session.get(SubstrateLocation, location_id)
    if loc is None or int(loc.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Location not found")
    article = session.get(SubstrateArticle, article_id)
    if article is None or int(article.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Article not found")

    payload = [o.model_dump() for o in body.occurrences]
    created = replace_mention_occurrences_for_article(
        session,
        article_id=article_id,
        location_id=location_id,
        occurrences_in=payload,
    )
    session.commit()
    enqueue_semantic_reindex(
        project_id=int(proj.id),
        article_id=article_id,
        entity_type="location",
    )
    out: list[MentionOccurrenceOut] = []
    for row in created:
        if row.id is None:
            continue
        out.append(
            MentionOccurrenceOut(
                id=int(row.id),
                mention_text=str(row.mention_text),
                quote_text=row.quote_text,
                start_char=row.start_char,
                end_char=row.end_char,
                occurrence_order=row.occurrence_order,
                suppressed=bool(row.suppressed),
                source_kind=str(row.source_kind),
            )
        )
    return ReplaceMentionOccurrencesResponse(occurrences=out)


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
