"""DBOutput persistence concurrency gate."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace

from worker.nodes import db_output
from worker.substrate.canonical.parallel_llm import run_callables_parallel


def test_dboutput_max_concurrent_persists_defaults_to_twelve(monkeypatch) -> None:
    monkeypatch.delenv("DBOUTPUT_MAX_CONCURRENT_PERSISTS", raising=False)
    assert db_output._dboutput_max_concurrent_persists() == 12


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


def test_persist_slot_logs_only_slow_waits(monkeypatch, caplog) -> None:
    class FakeLock:
        def acquire(self, *, blocking: bool) -> bool:
            return True

        def release(self) -> None:
            return None

    class FakeRedis:
        def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> FakeLock:
            return FakeLock()

    # Each acquire reads the clock twice: the first wait is 0.5 s, the second 2 s.
    ticks = iter([0.0, 0.5, 10.0, 12.0])
    monkeypatch.setattr(db_output.time, "perf_counter", ticks.__next__)
    lease = db_output._PersistSlotLease(FakeRedis(), 1)

    with caplog.at_level("INFO", logger=db_output.logger.name):
        lease.acquire()
        lease.release()
        lease.acquire()
        lease.release()

    messages = [r.getMessage() for r in caplog.records if "persist_slot" in r.getMessage()]
    assert messages == ["dboutput_persist_slot_acquired wait_ms=2000.0"]


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
        assert kwargs["embed_semantic"] is False
        events.append("persist")
        return {
            "success": True,
            "article_id": 42,
            "text": "Article text",
            "connections": None,
            "consolidated_domain_keys": [],
            "semantic_indexing": {"enabled": False, "status": "not_enabled"},
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
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: object())

    result = db_output.run_db_output({}, {"data": {"text": "Article text"}})

    assert result["connections"]["status"] == "succeeded"
    assert events.index("gate_exit") < events.index("inference")
    assert llm_kwargs[0]["allow_max_tokens_bump"] is False


def test_run_db_output_releases_persist_slot_before_semantic_embedding(
    monkeypatch,
) -> None:
    events: list[str] = []

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

    class FakeSettings:
        semantic_indexing_enabled = True
        auto_connections_enabled = False

        @classmethod
        def from_node_params(cls, _params: object) -> FakeSettings:
            return cls()

    def fake_persist(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["embed_semantic"] is False
        events.append("persist")
        return {
            "success": True,
            "article_id": 42,
            "text": "Article text",
            "consolidated_domain_keys": ["location"],
            "semantic_indexing": {"enabled": True, "status": "succeeded", "domains": []},
        }

    def fake_embed(*_args: object, **_kwargs: object) -> dict[str, object]:
        events.append("embed")
        return {"status": "succeeded", "embedded": 1}

    def fake_inference(*_args: object, **_kwargs: object) -> dict[str, object]:
        events.append("inference")
        return {"status": "skipped"}

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "7")
    monkeypatch.setenv("BACKFIELD_GRAPH_ID", "graph-1")
    monkeypatch.setenv("BACKFIELD_RUN_ID", "run-1")
    monkeypatch.setattr(db_output, "_dboutput_persist_slot", fake_slot)
    monkeypatch.setattr(db_output, "_persist_db_output_in_session", fake_persist)
    monkeypatch.setattr(
        db_output, "embed_pending_semantic_documents_for_db_output", fake_embed
    )
    monkeypatch.setattr(db_output, "run_auto_connections_for_db_output", fake_inference)
    monkeypatch.setattr(db_output, "DbOutputCanonicalSettings", FakeSettings)
    monkeypatch.setattr(db_output, "Session", FakeSession)
    monkeypatch.setattr(db_output, "_kick_webhook_dispatch_after_commit", lambda _session: None)
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: object())

    result = db_output.run_db_output({}, {"data": {"text": "Article text"}})

    assert result["semantic_indexing"]["embedding"]["status"] == "succeeded"
    assert events.index("gate_exit") < events.index("embed")
    assert events.index("embed") < events.index("inference")


def test_deadlock_retry_backoff_grows_and_is_capped() -> None:
    delays = [db_output._deadlock_retry_delay_s(attempt) for attempt in range(5)]
    assert 0.5 <= delays[0] <= 0.75
    assert 4.0 <= delays[3] <= 6.0
    assert 8.0 <= delays[4] <= 12.0
    assert db_output._DBOUTPUT_DEADLOCK_MAX_ATTEMPTS == 10


class _RecordingRedis:
    """Fake Redis whose locks record acquire/release order."""

    def __init__(self, events: list[str], *, fail_acquire_after: int | None = None) -> None:
        self.events = events
        self.acquires = 0
        self.fail_acquire_after = fail_acquire_after

    def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> object:
        outer = self

        class FakeLock:
            def acquire(self, *, blocking: bool) -> bool:
                if (
                    outer.fail_acquire_after is not None
                    and outer.acquires >= outer.fail_acquire_after
                ):
                    raise RuntimeError("redis down")
                outer.acquires += 1
                outer.events.append("slot_acquire")
                return True

            def release(self) -> None:
                outer.events.append("slot_release")

        return FakeLock()


def _install_recording_redis(monkeypatch, client: _RecordingRedis) -> None:
    monkeypatch.setenv("DBOUTPUT_MAX_CONCURRENT_PERSISTS", "1")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: client),
    )


def test_persist_slot_is_released_while_session_free_llm_calls_run(monkeypatch) -> None:
    events: list[str] = []
    _install_recording_redis(monkeypatch, _RecordingRedis(events))

    with db_output._dboutput_persist_slot():
        events.append("persist_before_llm")
        run_callables_parallel(
            [lambda: events.append("llm_call_1"), lambda: events.append("llm_call_2")],
            max_workers=1,
        )
        events.append("persist_after_llm")

    assert events == [
        "slot_acquire",
        "persist_before_llm",
        "slot_release",
        "llm_call_1",
        "llm_call_2",
        "slot_acquire",
        "persist_after_llm",
        "slot_release",
    ]


def test_persist_slot_is_retaken_even_when_llm_calls_raise(monkeypatch) -> None:
    events: list[str] = []
    _install_recording_redis(monkeypatch, _RecordingRedis(events))

    def failing_call() -> None:
        raise RuntimeError("llm failed")

    try:
        with db_output._dboutput_persist_slot():
            run_callables_parallel([failing_call], max_workers=1)
    except RuntimeError:
        pass

    # Re-taken after the failure so the outer release stays balanced.
    assert events == ["slot_acquire", "slot_release", "slot_acquire", "slot_release"]


def test_persist_slot_gate_fails_open_when_reacquire_fails(monkeypatch) -> None:
    events: list[str] = []
    _install_recording_redis(monkeypatch, _RecordingRedis(events, fail_acquire_after=1))

    with db_output._dboutput_persist_slot():
        run_callables_parallel([lambda: events.append("llm_call")], max_workers=1)
        events.append("persist_after_llm")

    assert events == ["slot_acquire", "slot_release", "llm_call", "persist_after_llm"]


def test_llm_batches_outside_persist_run_without_a_slot() -> None:
    ran: list[int] = []
    run_callables_parallel([lambda: ran.append(1)], max_workers=1)
    assert ran == [1]
