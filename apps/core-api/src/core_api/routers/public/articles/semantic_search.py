"""POST /public/v1/projects/{project_slug}/articles/semantic-search."""

from __future__ import annotations

from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.query_embedding import SemanticQueryEmbedding, embed_semantic_search_query
from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import enrich_articles_with_counts
from backfield_entities.public.article_semantic_search import (
    PublicArticleSemanticSearchItemOut,
    PublicArticleSemanticSearchParams,
    search_public_articles_semantic,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    INCLUDE_PARAM_DESCRIPTION,
    META_PARAM_DESCRIPTION,
    parse_article_includes,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicArticleSemanticSearchIn(BaseModel):
    query: str = Field(min_length=1, description="Natural-language search text")
    meta_type: str | None = Field(
        default=None,
        description="Include articles with a metadata row of this type",
    )
    meta_category: str | None = Field(
        default=None,
        description="With meta_type, include articles with this metadata category",
    )
    exclude_meta_type: str | None = Field(
        default=None,
        description="Exclude articles with a metadata row of this type",
    )
    exclude_meta_category: str | None = Field(
        default=None,
        description="With exclude_meta_type, exclude articles with this metadata category",
    )
    meta: list[str] = Field(default_factory=list, description=META_PARAM_DESCRIPTION)
    pub_date_from: str | None = None
    pub_date_to: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    use_hyde: bool = Field(
        default=False,
        description=(
            "Generate a hypothetical news passage from the query, embed that text, "
            "and search article embeddings against it (HyDE)"
        ),
    )
    include: list[str] = Field(default_factory=list, description=INCLUDE_PARAM_DESCRIPTION)


class PublicArticleSemanticSearchOut(BaseModel):
    query: str
    embedding_model: str | None = None
    embedding_model_config_id: str | None = None
    hyde_used: bool = False
    hypothetical_document: str | None = None
    hyde_model: str | None = None
    hyde_model_config_id: str | None = None
    items: list[PublicArticleSemanticSearchItemOut]
    pagination: PaginationOut


def _embedding_http_error(exc: EmbeddingConfigurationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _provider_model_id(litellm_model: str) -> str:
    if "/" in litellm_model:
        _, _, rest = litellm_model.partition("/")
        return rest or litellm_model
    return litellm_model


@router.post("/semantic-search", response_model=PublicArticleSemanticSearchOut)
def search_project_articles_semantic(
    body: PublicArticleSemanticSearchIn,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleSemanticSearchOut:
    """Search project articles by semantic similarity when embeddings exist."""
    query = body.query.strip()
    includes = parse_article_includes(body.include)
    try:
        embedding: SemanticQueryEmbedding = embed_semantic_search_query(
            session,
            project_id=int(project.id),  # type: ignore[arg-type]
            query=query,
            use_hyde=body.use_hyde,
        )
    except EmbeddingConfigurationError as exc:
        raise _embedding_http_error(exc) from exc

    params = PublicArticleSemanticSearchParams(
        meta_type=body.meta_type,
        meta_category=body.meta_category,
        exclude_meta_type=body.exclude_meta_type,
        exclude_meta_category=body.exclude_meta_category,
        meta_clauses=parse_meta_clauses(body.meta),
        pub_date_from=parse_optional_date(body.pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(body.pub_date_to, param_name="pub_date_to"),
        limit=body.limit,
        offset=body.offset,
    )
    items, total = search_public_articles_semantic(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        query_vector=embedding.vector,
        embedding_model_config_id=embedding.model_config_id,
        embedding_provider_model_id=_provider_model_id(embedding.embedding_model),
        params=params,
    )
    if "counts" in includes:
        enrich_articles_with_counts(session, items)
    return PublicArticleSemanticSearchOut(
        query=query,
        embedding_model=embedding.embedding_model,
        embedding_model_config_id=embedding.model_config_id,
        hyde_used=embedding.hyde_used,
        hypothetical_document=embedding.hypothetical_document,
        hyde_model=embedding.hyde_model,
        hyde_model_config_id=embedding.hyde_model_config_id,
        items=items,
        pagination=PaginationOut(limit=body.limit, offset=body.offset, total=total),
    )
