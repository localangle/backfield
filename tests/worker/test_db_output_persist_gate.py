"""DBOutput persistence concurrency gate."""

from __future__ import annotations

import sys
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
