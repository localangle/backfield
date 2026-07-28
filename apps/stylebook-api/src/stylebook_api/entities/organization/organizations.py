"""Project-scoped substrate organizations (Stylebook review, ``project_slug``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_db.text_sanitize import strip_nul_bytes
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.organization.persist import (
    link_substrate_to_canonical_atomic,
    requeue_substrate_after_story_remove,
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.organization.types import (
    ORGANIZATION_NATURE_VALUES,
    normalize_organization_type,
    organization_identity_fingerprint,
)
from backfield_entities.ingest.semantic_indexing.cleanup import (
    delete_semantic_documents_for_organization,
)
from backfield_entities.occurrence_spans import find_proven_occurrence_span
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id
from stylebook_api.mention_occurrences import replace_organization_mention_occurrences_for_article
from stylebook_api.semantic_reindex import enqueue_semantic_reindex

router = APIRouter(prefix="/v1", tags=["organizations"])


def _project_by_slug(session: Session, slug: str):
    return project_by_slug(session, slug)


def _require_stylebook_id(
    session: Session,
    project,
    stylebook_slug: str | None = None,
) -> int:
    return require_stylebook_id(session, project, stylebook_slug=stylebook_slug)


class LinkCanonicalBody(BaseModel):
    stylebook_organization_canonical_id: UUID


class LinkCanonicalResponse(BaseModel):
    changed: bool


def _manual_organization_type(value: str | None) -> str | None:
    return normalize_organization_type(value)


@router.post("/organizations/{organization_id}/unlink-canonical")
def unlink_substrate_from_canonical_route(
    organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        unlink_substrate_from_canonical(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            provenance="stylebook_ui_unlink",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session.commit()
    return {"message": "unlinked"}


@router.post(
    "/organizations/{organization_id}/link-canonical",
    response_model=LinkCanonicalResponse,
)
def link_substrate_to_canonical_route(
    organization_id: int,
    body: LinkCanonicalBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkCanonicalResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            target_canonical_id=str(body.stylebook_organization_canonical_id),
            provenance="stylebook_ui_link",
        )
    except ValueError as e:
        msg = str(e)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=409, detail=msg) from e
    session.commit()
    return LinkCanonicalResponse(changed=changed)


def _normalize_organization_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class SubstrateOrganizationResponse(BaseModel):
    id: int
    name: str
    organization_type: str | None = None
    status: str
    canonical_link_status: str | None = None
    stylebook_organization_canonical_id: str | None = None


@router.get("/organizations/{organization_id}", response_model=SubstrateOrganizationResponse)
def get_substrate_organization(
    organization_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstrateOrganizationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return SubstrateOrganizationResponse(
        id=int(organization.id),  # type: ignore[arg-type]
        name=str(organization.name),
        organization_type=organization.organization_type,
        status=str(organization.status),
        canonical_link_status=str(organization.canonical_link_status or ""),
        stylebook_organization_canonical_id=organization.stylebook_organization_canonical_id,
    )


class PatchSubstrateOrganizationBody(BaseModel):
    name: str | None = None
    organization_type: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] | None = None


@router.patch("/organizations/{organization_id}", response_model=SubstrateOrganizationResponse)
def patch_substrate_organization(
    organization_id: int,
    body: PatchSubstrateOrganizationBody,
    project_slug: str = Query(...),
    article_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstrateOrganizationResponse:
    """Update a substrate organization (and optional article mention editorial fields)."""
    from backfield_db import SubstrateOrganizationMention

    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        organization.name = name
        organization.normalized_name = _normalize_organization_name(name)
    if body.organization_type is not None:
        organization.organization_type = _manual_organization_type(
            body.organization_type.strip() or None
        )

    organization.identity_fingerprint = organization_identity_fingerprint(
        normalized_name=str(organization.normalized_name),
        organization_type=organization.organization_type,
    )
    session.add(organization)

    if article_id is not None:
        mention = session.exec(
            select(SubstrateOrganizationMention).where(
                SubstrateOrganizationMention.article_id == article_id,
                SubstrateOrganizationMention.organization_id == organization_id,
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        ).first()
        if mention is not None:
            if body.role_in_story is not None:
                mention.role_in_story = body.role_in_story.strip() or None
            if body.nature is not None:
                nature = body.nature.strip().lower()
                mention.nature = nature if nature in ORGANIZATION_NATURE_VALUES else "other"
            if body.nature_secondary_tags is not None:
                tags = [
                    t.strip().lower()
                    for t in body.nature_secondary_tags
                    if isinstance(t, str) and t.strip()
                ]
                mention.nature_secondary_tags_json = [
                    t for t in tags if t in ORGANIZATION_NATURE_VALUES
                ] or None
            mention.edited = True
            session.add(mention)

    session.commit()
    session.refresh(organization)
    return SubstrateOrganizationResponse(
        id=int(organization.id),  # type: ignore[arg-type]
        name=str(organization.name),
        organization_type=organization.organization_type,
        status=str(organization.status),
        canonical_link_status=str(organization.canonical_link_status or ""),
        stylebook_organization_canonical_id=organization.stylebook_organization_canonical_id,
    )


class CreateOrganizationFromArticleEvidenceBody(BaseModel):
    article_id: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    mention_text: str = Field(min_length=1)
    quote_text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)
    organization_type: str | None = None
    nature: str | None = None
    role_in_story: str | None = None


class CreateOrganizationFromArticleEvidenceResponse(BaseModel):
    organization: SubstrateOrganizationResponse
    mention_id: int
    occurrence_id: int
    anchor: str


@router.post(
    "/organizations/from-article-evidence",
    response_model=CreateOrganizationFromArticleEvidenceResponse,
)
def create_organization_from_article_evidence(
    body: CreateOrganizationFromArticleEvidenceBody,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CreateOrganizationFromArticleEvidenceResponse:
    """Create a saved organization from a manually selected article passage."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))

    name = body.name.strip()
    mention_text = strip_nul_bytes(body.mention_text.strip())
    quote_text = strip_nul_bytes(body.quote_text.strip())
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
    occurrence_span = find_proven_occurrence_span(
        article_text=article_text,
        evidence_texts=(quote_text, mention_text),
        proposed_span=(body.start_char, body.end_char),
    )

    organization_type = _manual_organization_type(
        body.organization_type.strip() if body.organization_type else None
    )
    normalized_name = _normalize_organization_name(name)
    nature: str | None = None
    if body.nature is not None:
        nature_raw = body.nature.strip().lower()
        nature = nature_raw if nature_raw in ORGANIZATION_NATURE_VALUES else "other"

    organization = SubstrateOrganization(
        project_id=int(proj.id),
        name=name,
        normalized_name=normalized_name,
        organization_type=organization_type,
        status="active",
        canonical_link_status=CANONICAL_LINK_PENDING,
        source_kind="manual_add",
        source_details_json={
            "source": "agate_review_add_organization",
            "run_id": run_id,
        },
        identity_fingerprint=organization_identity_fingerprint(
            normalized_name=normalized_name,
            organization_type=organization_type,
        ),
    )
    session.add(organization)
    session.flush()
    if organization.id is None:
        raise HTTPException(status_code=500, detail="Organization could not be created")
    anchor = f"user_organization:{int(organization.id)}"
    organization.source_details_json = {
        "source": "agate_review_add_organization",
        "run_id": run_id,
        "raw_entry_id": anchor,
    }

    mention = SubstrateOrganizationMention(
        article_id=int(article.id),  # type: ignore[arg-type]
        organization_id=int(organization.id),
        role_in_story=body.role_in_story.strip() if body.role_in_story else None,
        nature=nature,
        added=True,
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_organization", "run_id": run_id},
    )
    session.add(mention)
    session.flush()
    if mention.id is None:
        raise HTTPException(status_code=500, detail="Organization mention could not be created")

    occurrence = SubstrateOrganizationMentionOccurrence(
        organization_mention_id=int(mention.id),
        source_kind="manual_add",
        source_details_json={"source": "agate_review_add_organization", "run_id": run_id},
        mention_text=mention_text,
        quote_text=quote_text,
        start_char=occurrence_span[0] if occurrence_span else None,
        end_char=occurrence_span[1] if occurrence_span else None,
        occurrence_order=0,
        labels_json=[],
        suppressed=False,
    )
    session.add(occurrence)
    session.commit()
    enqueue_semantic_reindex(
        project_id=int(proj.id),
        article_id=body.article_id,
        entity_type="organization",
    )
    session.refresh(organization)
    session.refresh(mention)
    session.refresh(occurrence)

    return CreateOrganizationFromArticleEvidenceResponse(
        organization=SubstrateOrganizationResponse(
            id=int(organization.id),  # type: ignore[arg-type]
            name=str(organization.name),
            organization_type=organization.organization_type,
            status=str(organization.status),
            canonical_link_status=str(organization.canonical_link_status or ""),
            stylebook_organization_canonical_id=organization.stylebook_organization_canonical_id,
        ),
        mention_id=int(mention.id),  # type: ignore[arg-type]
        occurrence_id=int(occurrence.id),  # type: ignore[arg-type]
        anchor=anchor,
    )


@router.delete("/organizations/{organization_id}")
def delete_substrate_organization(
    organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    article_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Soft-delete story mentions; remove substrate row when no active mentions remain."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")

    mention_filters: list[ColumnElement[bool]] = [
        SubstrateOrganizationMention.organization_id == organization_id,
        SubstrateOrganizationMention.deleted == False,  # noqa: E712
    ]
    if article_id is not None:
        mention_filters.append(SubstrateOrganizationMention.article_id == article_id)

    mentions = session.exec(select(SubstrateOrganizationMention).where(*mention_filters)).all()
    article_ids = {int(mention.article_id) for mention in mentions}
    for mention in mentions:
        mention.deleted = True
        session.add(mention)
    session.flush()

    remaining = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganizationMention)
            .where(
                SubstrateOrganizationMention.organization_id == organization_id,
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
            )
        )
        or 0
    )

    organization_deleted = False
    candidates_created = 0
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    if remaining == 0:
        if requeue_substrate_after_story_remove(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            provenance="agate_review_delete",
        ):
            candidates_created = 1
        delete_semantic_documents_for_organization(
            session,
            organization_id=organization_id,
            project_id=int(proj.id),
        )
        session.delete(organization)
        organization_deleted = True

    session.commit()
    for aid in article_ids:
        enqueue_semantic_reindex(
            project_id=int(proj.id),
            article_id=aid,
            entity_type="organization",
        )
    return {
        "message": "deleted",
        "mentions_removed": len(mentions),
        "organization_deleted": organization_deleted,
        "candidates_created": candidates_created,
    }


class OrganizationMentionOccurrenceIn(BaseModel):
    id: int | None = None
    client_id: str | None = None
    mention_text: str = Field(min_length=1)
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool = False
    is_quote: bool = False


class OrganizationMentionOccurrenceOut(BaseModel):
    id: int
    mention_text: str
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool
    source_kind: str


class ReplaceOrganizationMentionOccurrencesIn(BaseModel):
    occurrences: list[OrganizationMentionOccurrenceIn] = Field(default_factory=list, max_length=50)


class ReplaceOrganizationMentionOccurrencesResponse(BaseModel):
    occurrences: list[OrganizationMentionOccurrenceOut]


@router.put(
    "/organizations/{organization_id}/mention-occurrences",
    response_model=ReplaceOrganizationMentionOccurrencesResponse,
)
def replace_organization_mention_occurrences(
    organization_id: int,
    body: ReplaceOrganizationMentionOccurrencesIn,
    project_slug: str = Query(...),
    article_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ReplaceOrganizationMentionOccurrencesResponse:
    """Replace all active mention occurrences for one article+organization (Agate Review)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    article = session.get(SubstrateArticle, article_id)
    if article is None or int(article.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Article not found")

    payload = [o.model_dump() for o in body.occurrences]
    created = replace_organization_mention_occurrences_for_article(
        session,
        article_id=article_id,
        organization_id=organization_id,
        occurrences_in=payload,
    )
    session.commit()
    enqueue_semantic_reindex(
        project_id=int(proj.id),
        article_id=article_id,
        entity_type="organization",
    )
    out: list[OrganizationMentionOccurrenceOut] = []
    for row in created:
        if row.id is None:
            continue
        out.append(
            OrganizationMentionOccurrenceOut(
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
    return ReplaceOrganizationMentionOccurrencesResponse(occurrences=out)
