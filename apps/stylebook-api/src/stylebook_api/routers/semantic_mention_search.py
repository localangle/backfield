"""Semantic mention search endpoints (Issue 9)."""

from __future__ import annotations

from typing import Any, Literal

from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.query_embedding import SemanticQueryEmbedding, embed_semantic_search_query
from backfield_auth.gate import require_project_access
from backfield_entities.ingest.semantic_indexing.search import (
    search_location_semantic_mentions,
    search_person_semantic_mentions,
)
from backfield_entities.ingest.semantic_indexing.search_contract import (
    LocationSemanticSearchFilters,
    PersonSemanticSearchFilters,
    QuoteStatusFilter,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.pagination import empty_page_metadata, pagination_flags
from stylebook_api.helpers.project_scope import project_by_slug

router = APIRouter(prefix="/v1", tags=["semantic-mentions"])


class SemanticMentionSearchIn(BaseModel):
    """Shared semantic mention search request body."""

    query: str = Field(min_length=1)
    article_id: int | None = Field(default=None, ge=1)
    canonical_id: str | None = None
    entity_id: int | None = Field(default=None, ge=1)
    mention_id: int | None = Field(default=None, ge=1)
    occurrence_id: int | None = Field(default=None, ge=1)
    active_only: bool = True
    quote_status: QuoteStatusFilter = "any"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    use_hyde: bool = False


class PersonSemanticMentionSearchIn(SemanticMentionSearchIn):
    person_type: str | None = None
    public_figure: bool | None = None
    nature: str | None = None
    title: str | None = None
    affiliation: str | None = None


class LocationSemanticMentionSearchIn(SemanticMentionSearchIn):
    location_type: str | None = None


class SemanticMentionSearchResultOut(BaseModel):
    semantic_document_id: int
    entity_type: Literal["person", "location"]
    score: float
    article: dict[str, Any]
    entity: dict[str, Any]
    canonical: dict[str, Any] | None = None
    mention: dict[str, Any]
    occurrence: dict[str, Any]
    search_text: str


class SemanticMentionSearchOut(BaseModel):
    query: str
    embedding_model: str | None = None
    embedding_model_config_id: str | None = None
    hyde_used: bool = False
    hypothetical_document: str | None = None
    hyde_model: str | None = None
    hyde_model_config_id: str | None = None
    total: int
    limit: int
    offset: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool
    results: list[SemanticMentionSearchResultOut]


def _embedding_http_error(exc: EmbeddingConfigurationError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _filters_from_body(body: SemanticMentionSearchIn) -> dict[str, Any]:
    return {
        "article_id": body.article_id,
        "canonical_id": body.canonical_id,
        "entity_id": body.entity_id,
        "mention_id": body.mention_id,
        "occurrence_id": body.occurrence_id,
        "active_only": body.active_only,
        "quote_status": body.quote_status,
    }


def _response_from_search(
    *,
    query: str,
    embedding: SemanticQueryEmbedding,
    search_result: Any,
    limit: int,
    offset: int,
) -> SemanticMentionSearchOut:
    page_len = len(search_result.hits)
    if page_len == 0:
        page, per_page, has_next, has_prev = empty_page_metadata(limit=limit, offset=offset)
    else:
        page = (offset // limit) + 1 if limit > 0 else 1
        per_page = limit
        has_next, has_prev = pagination_flags(
            total=search_result.total,
            limit=limit,
            offset=offset,
            page_len=page_len,
        )
    return SemanticMentionSearchOut(
        query=query,
        embedding_model=embedding.embedding_model,
        embedding_model_config_id=embedding.model_config_id,
        hyde_used=embedding.hyde_used,
        hypothetical_document=embedding.hypothetical_document,
        hyde_model=embedding.hyde_model,
        hyde_model_config_id=embedding.hyde_model_config_id,
        total=search_result.total,
        limit=limit,
        offset=offset,
        page=page,
        per_page=per_page,
        has_next=has_next,
        has_prev=has_prev,
        results=[
            SemanticMentionSearchResultOut(
                semantic_document_id=hit.semantic_document_id,
                entity_type=hit.entity_type,  # type: ignore[arg-type]
                score=hit.score,
                article=hit.article,
                entity=hit.entity,
                canonical=hit.canonical,
                mention=hit.mention,
                occurrence=hit.occurrence,
                search_text=hit.search_text,
            )
            for hit in search_result.hits
        ],
    )


@router.post("/people/semantic-mentions/search", response_model=SemanticMentionSearchOut)
def search_person_semantic_mentions_route(
    body: PersonSemanticMentionSearchIn,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SemanticMentionSearchOut:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    try:
        embedding = embed_semantic_search_query(
            session,
            project_id=int(proj.id),
            query=body.query,
            use_hyde=body.use_hyde,
        )
    except EmbeddingConfigurationError as exc:
        raise _embedding_http_error(exc) from exc

    filters = PersonSemanticSearchFilters(
        **_filters_from_body(body),
        person_type=body.person_type,
        public_figure=body.public_figure,
        nature=body.nature,
        title=body.title,
        affiliation=body.affiliation,
    )
    search_result = search_person_semantic_mentions(
        session,
        project_id=int(proj.id),
        query_vector=embedding.vector,
        filters=filters,
        limit=body.limit,
        offset=body.offset,
    )
    return _response_from_search(
        query=body.query.strip(),
        embedding=embedding,
        search_result=search_result,
        limit=body.limit,
        offset=body.offset,
    )


@router.post("/locations/semantic-mentions/search", response_model=SemanticMentionSearchOut)
def search_location_semantic_mentions_route(
    body: LocationSemanticMentionSearchIn,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SemanticMentionSearchOut:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    try:
        embedding = embed_semantic_search_query(
            session,
            project_id=int(proj.id),
            query=body.query,
            use_hyde=body.use_hyde,
        )
    except EmbeddingConfigurationError as exc:
        raise _embedding_http_error(exc) from exc

    filters = LocationSemanticSearchFilters(
        **_filters_from_body(body),
        location_type=body.location_type,
    )
    search_result = search_location_semantic_mentions(
        session,
        project_id=int(proj.id),
        query_vector=embedding.vector,
        filters=filters,
        limit=body.limit,
        offset=body.offset,
    )
    return _response_from_search(
        query=body.query.strip(),
        embedding=embedding,
        search_result=search_result,
        limit=body.limit,
        offset=body.offset,
    )
