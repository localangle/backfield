"""Worker tests for semantic re-index jobs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backfield_entities.ingest.semantic_indexing.embedding_contract import EmbeddingRunSummary
from backfield_entities.ingest.semantic_indexing.reindex_contract import SemanticReindexScope
from backfield_entities.ingest.semantic_indexing.sync_contract import (
    SemanticSyncResult,
    SemanticSyncSummary,
)
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from worker.semantic_indexing.reindex import run_semantic_reindex_for_scope


@patch("worker.semantic_indexing.reindex.embed_pending_semantic_documents")
@patch("worker.semantic_indexing.reindex.sync_semantic_documents_for_article")
def test_run_semantic_reindex_reuses_sync_and_embed(
    mock_sync: MagicMock,
    mock_embed: MagicMock,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    mock_sync.return_value = SemanticSyncResult(
        summaries=(SemanticSyncSummary(entity_type="person", updated=1, pending=1),)
    )
    mock_embed.return_value = EmbeddingRunSummary(
        status="succeeded",
        indexed=1,
        pending=1,
    )

    with Session(engine) as session:
        result = run_semantic_reindex_for_scope(
            session,
            SemanticReindexScope(project_id=1, article_id=2, entity_type="person"),
        )

    mock_sync.assert_called_once()
    mock_embed.assert_called_once()
    assert result["article_id"] == 2
    assert result["embedding"]["status"] == "succeeded"


@patch("worker.semantic_indexing.reindex.embed_pending_semantic_documents")
@patch("worker.semantic_indexing.reindex.sync_semantic_documents_for_article")
def test_run_semantic_reindex_embedding_failure_does_not_raise(
    mock_sync: MagicMock,
    mock_embed: MagicMock,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    mock_sync.return_value = SemanticSyncResult(
        summaries=(SemanticSyncSummary(entity_type="person", updated=1),)
    )
    mock_embed.return_value = EmbeddingRunSummary(status="failed", failed=1, error="provider down")

    with Session(engine) as session:
        result = run_semantic_reindex_for_scope(
            session,
            SemanticReindexScope(project_id=1, article_id=2, entity_type="person"),
        )

    assert result["embedding"]["status"] == "failed"
