"""Worker semantic embedding batch orchestration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backfield_ai.embeddings import EmbeddingItemResult, LiteLLMEmbeddingBatchResult
from backfield_db import AgateRun, SubstratePersonSemanticDocument
from backfield_stylebook.semantic_indexing.db_output import sync_semantic_documents_after_db_output
from backfield_stylebook.semantic_indexing.embedding_contract import EmbeddingApplySummary
from sqlmodel import Session, SQLModel, create_engine, select
from worker.semantic_indexing.embed import embed_pending_semantic_documents_for_db_output
from worker.substrate import persist_from_consolidated

from tests.worker.test_person_substrate_persistence import _sample_person_entry
from tests.worker.test_substrate_persistence import _bootstrap_project
from tests.worker.test_worker_db_output_semantic_indexing import _seed_project_embedding_model


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


@patch("worker.semantic_indexing.embed.apply_embedding_batch_outcomes")
@patch("worker.semantic_indexing.embed.embed_texts_for_model_config")
def test_embed_pending_batches_provider_calls(
    mock_embed: MagicMock,
    mock_apply: MagicMock,
) -> None:
    mock_embed.return_value = LiteLLMEmbeddingBatchResult(
        litellm_model="openai/text-embedding-3-small",
        provider="openai",
        provider_model_id="text-embedding-3-small",
        dimensions=3,
        items=[
            EmbeddingItemResult(index=0, vector=[0.1, 0.2, 0.3]),
            EmbeddingItemResult(index=1, vector=[0.4, 0.5, 0.6]),
        ],
        prompt_tokens=10,
        total_tokens=10,
        estimated_cost=None,
        currency="USD",
        cost_estimate_incomplete=True,
        cost_estimate_source="unavailable",
        latency_ms=5,
        batch_error=None,
    )
    mock_apply.return_value = EmbeddingApplySummary(indexed=2)

    engine = _engine()
    body = (
        "Mayor Jane Smith announced a new policy today. "
        '"This will benefit all residents," Smith said.'
    )
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-embed-batch", project_slug="proj-embed-batch"
        )
        _seed_project_embedding_model(session, project_id)
        session.add(AgateRun(id="run-embed-batch", graph_id="g", status="pending"))
        session.commit()

        persist_result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="g",
            run_id="run-embed-batch",
            consolidated={
                "text": body,
                "url": "https://example.com/embed-batch",
                "people": [_sample_person_entry()],
            },
            db_output_params={"stylebook_matching_enabled": False},
        )
        sync_semantic_documents_after_db_output(
            session,
            project_id=project_id,
            article_id=persist_result.article_id,
            consolidated_domain_keys=persist_result.consolidated_domain_keys,
        )
        session.commit()

        doc_row = session.exec(select(SubstratePersonSemanticDocument)).first()
        assert doc_row is not None
        article_id_val = int(doc_row.article_id)

        result = embed_pending_semantic_documents_for_db_output(
            session,
            project_id=project_id,
            article_id=article_id_val,
            consolidated_domain_keys=("people",),
        )

    assert result.status == "succeeded"
    assert result.indexed == 2
    assert result.batches == 1
    mock_embed.assert_called_once()
    assert len(mock_embed.call_args.kwargs["texts"]) == 2
    mock_apply.assert_called_once()
