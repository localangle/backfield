"""Embed natural-language queries for semantic mention search (Issue 9)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from backfield_ai.embeddings import EmbeddingConfigurationError, embed_texts_for_model_config
from backfield_ai.hyde import generate_hypothetical_document
from backfield_ai.model_resolve import resolve_semantic_embedding_model_config_id


@dataclass(frozen=True)
class SemanticQueryEmbedding:
    """One query vector plus model metadata for search ranking."""

    vector: list[float]
    model_config_id: str
    embedding_model: str
    embedding_dimensions: int | None
    hyde_used: bool = False
    hypothetical_document: str | None = None
    hyde_model_config_id: str | None = None
    hyde_model: str | None = None


def embed_semantic_search_query(
    session: Session,
    *,
    project_id: int,
    query: str,
    use_hyde: bool = False,
) -> SemanticQueryEmbedding:
    """Embed one search query using the project/org default semantic.embedding model."""
    text = query.strip()
    if not text:
        raise EmbeddingConfigurationError("Search query text is required.")

    hyde_model_config_id: str | None = None
    hyde_model: str | None = None
    hypothetical_document: str | None = None
    embed_text = text
    if use_hyde:
        hypothetical_document, hyde_model_config_id, hyde_model = generate_hypothetical_document(
            session,
            project_id=project_id,
            query=text,
        )
        embed_text = hypothetical_document

    model_config_id = resolve_semantic_embedding_model_config_id(session, project_id)
    result = embed_texts_for_model_config(
        session,
        project_id=project_id,
        model_config_id=model_config_id,
        texts=[embed_text],
    )
    if result.batch_error or not result.items or result.items[0].vector is None:
        message = result.batch_error or result.items[0].error_message or "Query embedding failed."
        raise EmbeddingConfigurationError(message)

    return SemanticQueryEmbedding(
        vector=list(result.items[0].vector),
        model_config_id=model_config_id,
        embedding_model=result.litellm_model,
        embedding_dimensions=result.dimensions,
        hyde_used=use_hyde,
        hypothetical_document=hypothetical_document,
        hyde_model_config_id=hyde_model_config_id,
        hyde_model=hyde_model,
    )
