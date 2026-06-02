"""Tests for semantic search query embedding helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingItemResult,
    LiteLLMEmbeddingBatchResult,
)
from backfield_ai.query_embedding import embed_semantic_search_query
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel


def test_embed_semantic_search_query_requires_non_empty_text() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(EmbeddingConfigurationError, match="required"):
            embed_semantic_search_query(session, project_id=1, query="  ")


@patch("backfield_ai.query_embedding.embed_texts_for_model_config")
@patch("backfield_ai.query_embedding.resolve_semantic_embedding_model_config_id")
def test_embed_semantic_search_query_returns_vector(
    mock_resolve: MagicMock,
    mock_embed: MagicMock,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    mock_resolve.return_value = "emb-search-test"
    mock_embed.return_value = LiteLLMEmbeddingBatchResult(
        litellm_model="openai/text-embedding-3-small",
        provider="openai",
        provider_model_id="text-embedding-3-small",
        dimensions=3,
        items=[EmbeddingItemResult(index=0, vector=[0.1, 0.2, 0.3])],
        prompt_tokens=1,
        total_tokens=1,
        estimated_cost=None,
        currency="USD",
        cost_estimate_incomplete=True,
        cost_estimate_source="unavailable",
        latency_ms=1,
    )

    with Session(engine) as session:
        out = embed_semantic_search_query(session, project_id=1, query="downtown crime")

    assert out.model_config_id == "emb-search-test"
    assert out.vector == [0.1, 0.2, 0.3]
