"""Embedding batches persist AI call records when worker tracking context is set."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import litellm
import pytest
from backfield_ai.constants import (
    AI_MODEL_KIND_EMBEDDING,
    COST_ESTIMATE_SOURCE_LITELLM,
)
from backfield_ai.embeddings import embed_texts_sync
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    persist_llm_attempt,
    reset_llm_tracking_context,
    set_llm_tracking_current_node,
)
from backfield_db import BackfieldAiCallRecord
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool


@pytest.fixture
def memory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BackfieldAiCallRecord.metadata.create_all(engine)
    return engine


@pytest.fixture
def memory_session(memory_engine) -> Session:
    with Session(memory_engine) as session:
        yield session


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_persists_call_record_when_tracked(
    mock_embedding: MagicMock,
    memory_engine,
    memory_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backfield_ai.tracking_context.get_engine", lambda: memory_engine)
    item0 = MagicMock(index=0, embedding=[0.1, 0.2])
    resp = MagicMock(data=[item0], usage=MagicMock(prompt_tokens=3, total_tokens=3))
    mock_embedding.return_value = resp
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 0.00001)

    tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(project_id=1, run_id="run-1"),
    )
    set_llm_tracking_current_node("db-out", "DBOutput")
    try:
        result = embed_texts_sync(
            litellm_model="openai/text-embedding-3-small",
            texts=["hello"],
            api_key="sk-test",
            model_config_id="cfg-embed-1",
        )
    finally:
        reset_llm_tracking_context(tok)

    assert result.batch_error is None
    assert result.estimated_cost == Decimal("0.00001")
    assert result.cost_estimate_source == COST_ESTIMATE_SOURCE_LITELLM

    rows = list(memory_session.exec(select(BackfieldAiCallRecord)).all())
    assert len(rows) == 1
    row = rows[0]
    assert row.model_kind == AI_MODEL_KIND_EMBEDDING
    assert row.model_config_id == "cfg-embed-1"
    assert row.run_id == "run-1"
    assert row.node_id == "db-out"
    assert row.node_type == "DBOutput"
    assert row.status == "succeeded"
    assert row.prompt_tokens == 3
    assert row.completion_tokens is None
    assert row.estimated_cost == Decimal("0.00001")


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_skips_persist_without_tracking_context(
    mock_embedding: MagicMock,
    memory_session: Session,
) -> None:
    item0 = MagicMock(index=0, embedding=[0.1, 0.2])
    resp = MagicMock(data=[item0], usage=MagicMock(prompt_tokens=2, total_tokens=2))
    mock_embedding.return_value = resp

    embed_texts_sync(
        litellm_model="openai/text-embedding-3-small",
        texts=["hello"],
        api_key="sk-test",
        track_attempt=True,
    )

    assert list(memory_session.exec(select(BackfieldAiCallRecord)).all()) == []


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_persists_failed_provider_call(
    mock_embedding: MagicMock,
    memory_engine,
    memory_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backfield_ai.tracking_context.get_engine", lambda: memory_engine)
    mock_embedding.side_effect = RuntimeError("rate limited")
    tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(project_id=2, run_id="run-2"),
    )
    try:
        result = embed_texts_sync(
            litellm_model="openai/text-embedding-3-small",
            texts=["a", "b"],
            api_key="sk-test",
        )
    finally:
        reset_llm_tracking_context(tok)

    assert result.batch_error == "rate limited"
    rows = list(memory_session.exec(select(BackfieldAiCallRecord)).all())
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].model_kind == AI_MODEL_KIND_EMBEDDING
    assert rows[0].error_type == "EmbeddingBatchError"


def test_persist_llm_attempt_noop_without_context() -> None:
    persist_llm_attempt(
        provider="openai",
        provider_model_id="text-embedding-3-small",
        status="succeeded",
        attempt_number=1,
        model_config_id=None,
        model_config_snapshot_json=None,
        prompt_tokens=1,
        completion_tokens=None,
        total_tokens=1,
        estimated_cost=Decimal("0"),
        currency="USD",
        cost_estimate_incomplete=False,
        latency_ms=10,
        provider_request_id=None,
        error_type=None,
        error_message=None,
        model_kind=AI_MODEL_KIND_EMBEDDING,
    )
