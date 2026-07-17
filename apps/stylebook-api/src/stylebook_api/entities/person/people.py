"""Project-scoped substrate people (Stylebook review, ``project_slug``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_db.text_sanitize import strip_nul_bytes
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.person.persist import (
    link_substrate_to_canonical_atomic,
    requeue_substrate_after_story_remove,
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.person.types import (
    PERSON_NATURE_VALUES,
    derive_person_sort_key,
    normalize_person_type,
    person_identity_fingerprint,
)
from backfield_entities.ingest.semantic_indexing.cleanup import delete_semantic_documents_for_person
from backfield_entities.ingest.semantic_indexing.reindex import (
    person_patch_affects_semantic_index,
    person_patch_entity_fields_changed,
)
from backfield_entities.occurrence_spans import find_proven_occurrence_span
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id
from stylebook_api.mention_occurrences import replace_person_mention_occurrences_for_article
from stylebook_api.semantic_reindex import (
    enqueue_semantic_reindex,
    enqueue_semantic_reindex_for_entity,
)

router = APIRouter(prefix="/v1", tags=["people"])


def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    return project_by_slug(session, slug)


def _require_stylebook_id(
    session: Session,
    project: BackfieldProject,
    stylebook_slug: str | None = None,
) -> int:
    return require_stylebook_id(session, project, stylebook_slug=stylebook_slug)


class LinkCanonicalBody(BaseModel):
    stylebook_person_canonical_id: UUID


class LinkCanonicalResponse(BaseModel):
    changed: bool


def _manual_person_type(value: str | None) -> str | None:
    """Normalize manual UI/API ``person_type`` to the bounded taxonomy."""
    return normalize_person_type(value)


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
    enqueue_semantic_reindex_for_entity(
        session,
        project_id=int(proj.id),
        entity_type="person",
        entity_id=person_id,
    )
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
    enqueue_semantic_reindex_for_entity(
        session,
        project_id=int(proj.id),
        entity_type="person",
        entity_id=person_id,
    )
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
    sort_key: str | None = None
    status: str
    canonical_link_status: str | None = None
    stylebook_person_canonical_id: str | None = None


@router.get("/people/{person_id}", response_model=SubstratePersonResponse)
def get_substrate_person(
    person_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstratePersonResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")
    return SubstratePersonResponse(
        id=int(person.id),  # type: ignore[arg-type]
        name=str(person.name),
        title=person.title,
        affiliation=person.affiliation,
        public_figure=bool(person.public_figure),
        person_type=person.person_type,
        sort_key=person.sort_key,
        status=str(person.status),
        canonical_link_status=str(person.canonical_link_status or ""),
        stylebook_person_canonical_id=person.stylebook_person_canonical_id,
    )


class PatchSubstratePersonBody(BaseModel):
    name: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    person_type: str | None = None
    sort_key: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] | None = None


def _maybe_enqueue_person_reindex_after_patch(
    session: Session,
    *,
    project_id: int,
    person_id: int,
    article_id: int | None,
    body: PatchSubstratePersonBody,
) -> None:
    if not person_patch_affects_semantic_index(body):
        return
    if article_id is not None:
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=project_id,
            entity_type="person",
            entity_id=person_id,
            article_id=article_id,
        )
    elif person_patch_entity_fields_changed(body):
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=project_id,
            entity_type="person",
            entity_id=person_id,
        )


def _enqueue_person_reindex_for_articles(
    *,
    project_id: int,
    article_ids: set[int],
) -> None:
    for aid in sorted(article_ids):
        enqueue_semantic_reindex(
            project_id=project_id,
            article_id=aid,
            entity_type="person",
        )


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

    person_type = _manual_person_type(body.person_type.strip() if body.person_type else None)
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
        sort_key=derive_person_sort_key(name),
        status="active",
        canonical_link_status=CANONICAL_LINK_PENDING,
        source_kind="manual_add",
        source_details_json={
            "source": "agate_review_add_person",
            "run_id": run_id,
        },
        identity_fingerprint=person_identity_fingerprint(
            normalized_name=normalized_name,
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
        entity_type="person",
    )
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
            sort_key=person.sort_key,
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
        person.sort_key = derive_person_sort_key(name, explicit=body.sort_key)
    elif body.sort_key is not None:
        person.sort_key = derive_person_sort_key(person.name, explicit=body.sort_key)
    if body.title is not None:
        person.title = body.title.strip() or None
    if body.affiliation is not None:
        person.affiliation = body.affiliation.strip() or None
    if body.public_figure is not None:
        person.public_figure = bool(body.public_figure)
    if body.person_type is not None:
        person.person_type = _manual_person_type(body.person_type.strip() or None)

    person.identity_fingerprint = person_identity_fingerprint(
        normalized_name=str(person.normalized_name),
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
    _maybe_enqueue_person_reindex_after_patch(
        session,
        project_id=int(proj.id),
        person_id=person_id,
        article_id=article_id,
        body=body,
    )
    session.refresh(person)
    return SubstratePersonResponse(
        id=int(person.id),  # type: ignore[arg-type]
        name=str(person.name),
        title=person.title,
        affiliation=person.affiliation,
        public_figure=bool(person.public_figure),
        person_type=person.person_type,
        sort_key=person.sort_key,
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
    article_ids = {int(mention.article_id) for mention in mentions}
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
        delete_semantic_documents_for_person(
            session,
            person_id=person_id,
            project_id=int(proj.id),
        )
        session.delete(person)
        person_deleted = True

    session.commit()
    _enqueue_person_reindex_for_articles(
        project_id=int(proj.id),
        article_ids=article_ids,
    )
    return {
        "message": "deleted",
        "mentions_removed": len(mentions),
        "person_deleted": person_deleted,
        "candidates_created": candidates_created,
    }


class PersonMentionOccurrenceIn(BaseModel):
    id: int | None = None
    client_id: str | None = None
    mention_text: str = Field(min_length=1)
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool = False
    is_quote: bool = False


class PersonMentionOccurrenceOut(BaseModel):
    id: int
    mention_text: str
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None
    suppressed: bool
    source_kind: str


class ReplacePersonMentionOccurrencesIn(BaseModel):
    occurrences: list[PersonMentionOccurrenceIn] = Field(default_factory=list, max_length=50)


class ReplacePersonMentionOccurrencesResponse(BaseModel):
    occurrences: list[PersonMentionOccurrenceOut]


@router.put(
    "/people/{person_id}/mention-occurrences",
    response_model=ReplacePersonMentionOccurrencesResponse,
)
def replace_person_mention_occurrences(
    person_id: int,
    body: ReplacePersonMentionOccurrencesIn,
    project_slug: str = Query(...),
    article_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ReplacePersonMentionOccurrencesResponse:
    """Replace all active mention occurrences for one article+person (Agate Review)."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Person not found")
    article = session.get(SubstrateArticle, article_id)
    if article is None or int(article.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Article not found")

    payload = [o.model_dump() for o in body.occurrences]
    created = replace_person_mention_occurrences_for_article(
        session,
        article_id=article_id,
        person_id=person_id,
        occurrences_in=payload,
    )
    session.commit()
    enqueue_semantic_reindex(
        project_id=int(proj.id),
        article_id=article_id,
        entity_type="person",
    )
    out: list[PersonMentionOccurrenceOut] = []
    for row in created:
        if row.id is None:
            continue
        out.append(
            PersonMentionOccurrenceOut(
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
    return ReplacePersonMentionOccurrencesResponse(occurrences=out)

