"""DBOutput persistence concurrency gate."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace

from worker.nodes import db_output


def test_dboutput_max_concurrent_persists_defaults_to_eight(monkeypatch) -> None:
    monkeypatch.delenv("DBOUTPUT_MAX_CONCURRENT_PERSISTS", raising=False)
    assert db_output._dboutput_max_concurrent_persists() == 8


def test_dboutput_max_concurrent_persists_respects_zero_disable(monkeypatch) -> None:
    monkeypatch.setenv("DBOUTPUT_MAX_CONCURRENT_PERSISTS", "0")
    assert db_output._dboutput_max_concurrent_persists() == 0


def test_dboutput_persist_slot_acquires_and_releases_redis_lock(monkeypatch) -> None:
    events: list[str] = []

    class FakeLock:
        def acquire(self, *, blocking: bool) -> bool:
            events.append(f"acquire:{blocking}")
            return True

        def release(self) -> None:
            events.append("release")

    class FakeRedis:
        def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> FakeLock:
            events.append(f"lock:{name}:{timeout}:{blocking_timeout}")
            return FakeLock()

    monkeypatch.setenv("DBOUTPUT_MAX_CONCURRENT_PERSISTS", "1")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: FakeRedis()),
    )

    with db_output._dboutput_persist_slot():
        events.append("inside")

    assert events == [
        "lock:backfield:dboutput:persist:0:1800:0",
        "acquire:False",
        "inside",
        "release",
    ]


def test_run_db_output_releases_persist_slot_before_connection_inference(
    monkeypatch,
) -> None:
    events: list[str] = []
    llm_kwargs: list[dict[str, object]] = []

    @contextmanager
    def fake_slot():
        events.append("gate_enter")
        try:
            yield
        finally:
            events.append("gate_exit")

    class FakeSession:
        def __init__(self, _engine: object) -> None:
            pass

        def __enter__(self) -> FakeSession:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def commit(self) -> None:
            events.append("commit")

    def fake_persist(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["infer_connections"] is False
        events.append("persist")
        return {
            "success": True,
            "article_id": 42,
            "text": "Article text",
            "connections": None,
        }

    def fake_inference(*_args: object, **kwargs: object) -> dict[str, object]:
        events.append("inference")
        call_llm = kwargs["call_llm"]
        call_llm(
            "prompt",
            model="test",
            force_json=True,
            temperature=0.0,
            model_config_id=None,
        )
        return {"status": "succeeded", "deferred_candidate_ids": []}

    def fake_call_llm(_prompt: str, **kwargs: object) -> str:
        llm_kwargs.append(kwargs)
        return '{"edges":[]}'

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "7")
    monkeypatch.setenv("BACKFIELD_GRAPH_ID", "graph-1")
    monkeypatch.setenv("BACKFIELD_RUN_ID", "run-1")
    monkeypatch.setattr(db_output, "_dboutput_persist_slot", fake_slot)
    monkeypatch.setattr(db_output, "_persist_db_output_in_session", fake_persist)
    monkeypatch.setattr(db_output, "run_auto_connections_for_db_output", fake_inference)
    monkeypatch.setattr(db_output, "call_llm", fake_call_llm)
    monkeypatch.setattr(db_output, "Session", FakeSession)
    monkeypatch.setattr(db_output, "_kick_webhook_dispatch_after_commit", lambda _session: None)
    monkeypatch.setattr(
        db_output,
        "_kick_deferred_connection_inference_after_commit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: object())

    result = db_output.run_db_output({}, {"data": {"text": "Article text"}})

    assert result["connections"]["status"] == "succeeded"
    assert events.index("gate_exit") < events.index("inference")
    assert llm_kwargs[0]["allow_max_tokens_bump"] is False
