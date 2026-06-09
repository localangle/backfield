"""Concurrent persist_llm_attempt calls must not corrupt the shared session."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from decimal import Decimal

import pytest
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    persist_llm_attempt,
    reset_llm_tracking_context,
)
from backfield_db import BackfieldAiCallRecord
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BackfieldAiCallRecord.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _persist_one(i: int) -> None:
    persist_llm_attempt(
        provider="openai",
        provider_model_id="gpt-test",
        status="succeeded",
        attempt_number=1,
        model_config_id=None,
        model_config_snapshot_json=None,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        estimated_cost=Decimal("0.001"),
        currency="USD",
        cost_estimate_incomplete=False,
        latency_ms=10,
        provider_request_id=f"req-{i}",
        error_type=None,
        error_message=None,
    )


def test_persist_llm_attempt_concurrent_writes(memory_session: Session) -> None:
    tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(session=memory_session, project_id=1, run_id="run-par"),
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(copy_context().run, _persist_one, i) for i in range(20)
            ]
            for fut in as_completed(futures):
                fut.result()
    finally:
        reset_llm_tracking_context(tok)

    rows = list(memory_session.exec(select(BackfieldAiCallRecord)).all())
    assert len(rows) == 20
