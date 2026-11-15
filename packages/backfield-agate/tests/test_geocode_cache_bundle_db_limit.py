"""GeocodeAgent cache lookups must not hold more pooled connections than allowed."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

# Import the runtime entry point first: importing the runner directly hits a circular import.
import agate_runtime.nodes.geocode_agent  # noqa: F401
from agate_nodes.geocode_agent import runner


def _count_peak_concurrent_lookups(monkeypatch, *, thread_count: int) -> int:
    active = 0
    peak = 0
    lock = threading.Lock()

    class FakeSession:
        def __init__(self, _engine: object) -> None:
            pass

        def __enter__(self) -> FakeSession:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def slow_resolve(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return SimpleNamespace(match_dict=None, ambiguous_tier1=False, tier2_sanity_failed=False)

    monkeypatch.setattr("sqlmodel.Session", FakeSession)
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: object())
    monkeypatch.setattr(
        "backfield_entities.ingest.geocode_cache.resolve.resolve_geocode_cache_strict_with_outcome",
        slow_resolve,
    )

    bundle = runner._build_geocode_cache_bundle(project_id=1, stylebook_id=1)
    threads = [
        threading.Thread(
            target=bundle["strict_resolve_with_outcome"], args=("Chicago, IL", "place", {})
        )
        for _ in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return peak


def test_cache_lookups_default_to_one_pooled_connection(monkeypatch) -> None:
    monkeypatch.delenv("GEOCODE_DB_MAX_CONCURRENT", raising=False)
    assert _count_peak_concurrent_lookups(monkeypatch, thread_count=8) == 1


def test_cache_lookup_limit_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("GEOCODE_DB_MAX_CONCURRENT", "2")
    assert _count_peak_concurrent_lookups(monkeypatch, thread_count=8) == 2
