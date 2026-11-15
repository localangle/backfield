"""Fleet-wide geocode Redis concurrency gate."""

from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agate_utils.geocoding import request_gate


def test_geocode_provider_max_concurrent_defaults(monkeypatch) -> None:
    monkeypatch.delenv("GEOCODE_PELIAS_MAX_CONCURRENT", raising=False)
    monkeypatch.delenv("GEOCODE_NOMINATIM_MAX_CONCURRENT", raising=False)
    monkeypatch.delenv("GEOCODE_GEOCODIO_MAX_CONCURRENT", raising=False)
    monkeypatch.delenv("GEOCODE_PELIAS_MAX_RPS", raising=False)
    assert request_gate.geocode_provider_max_concurrent("pelias") == 10
    assert request_gate.geocode_provider_max_concurrent("nominatim") == 1
    assert request_gate.geocode_provider_max_concurrent("geocodio") == 8
    assert request_gate.geocode_pelias_max_rps() == 10


def test_geocode_provider_max_concurrent_zero_disables(monkeypatch) -> None:
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "0")
    assert request_gate.geocode_provider_max_concurrent("pelias") == 0


def test_acquire_geocode_request_slot_acquires_and_releases(monkeypatch) -> None:
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

    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "1")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "0")
    monkeypatch.setenv("GEOCODE_REQUEST_GATE_TTL_S", "90")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: FakeRedis()),
    )

    with request_gate.acquire_geocode_request_slot("pelias"):
        events.append("inside")

    assert events == [
        "lock:backfield:geocode:pelias:slot:0:90:0",
        "acquire:False",
        "inside",
        "release",
    ]


def test_acquire_geocode_request_slot_raises_when_wait_budget_ends(monkeypatch) -> None:
    class BusyLock:
        def acquire(self, *, blocking: bool) -> bool:
            return False

    class BusyRedis:
        def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> BusyLock:
            return BusyLock()

    monkeypatch.setenv("GEOCODE_OVERPASS_MAX_CONCURRENT", "1")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: BusyRedis()),
    )

    with pytest.raises(request_gate.GateWaitTimeout):
        with request_gate.acquire_geocode_request_slot("overpass", max_wait_s=0.1):
            pass


def test_overpass_cooldown_round_trip(monkeypatch) -> None:
    store: dict[str, str] = {}

    class FakeRedis:
        def exists(self, key: str) -> int:
            return int(key in store)

        def set(self, key: str, value: str, *, ex: int) -> None:
            assert ex == 45
            store[key] = value

    monkeypatch.setenv("OVERPASS_COOLDOWN_S", "45")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: FakeRedis()),
    )

    assert request_gate.overpass_cooldown_active() is False
    request_gate.start_overpass_cooldown("test")
    assert request_gate.overpass_cooldown_active() is True


def test_overpass_cooldown_disabled_and_fails_open(monkeypatch) -> None:
    monkeypatch.setenv("OVERPASS_COOLDOWN_S", "0")
    assert request_gate.overpass_cooldown_active() is False

    monkeypatch.setenv("OVERPASS_COOLDOWN_S", "30")

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("no redis")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(from_url=boom))
    assert request_gate.overpass_cooldown_active() is False
    request_gate.start_overpass_cooldown("ignored")


def test_acquire_geocode_request_slot_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("GEOCODE_NOMINATIM_MAX_CONCURRENT", "0")
    with patch.object(request_gate, "logger") as logger:
        with request_gate.acquire_geocode_request_slot("nominatim"):
            pass
    logger.warning.assert_not_called()


def test_acquire_geocode_request_slot_fail_open_without_redis(monkeypatch) -> None:
    monkeypatch.setenv("GEOCODE_GEOCODIO_MAX_CONCURRENT", "2")

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("no redis")

    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=boom),
    )
    with request_gate.acquire_geocode_request_slot("geocodio"):
        ran = True
    assert ran is True


def test_async_acquire_takes_and_releases_slot(monkeypatch) -> None:
    events: list[str] = []

    class FakeLock:
        def acquire(self, *, blocking: bool) -> bool:
            events.append("acquire")
            return True

        def release(self) -> None:
            events.append("release")

    class FakeRedis:
        def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> FakeLock:
            events.append(f"lock:{name}")
            return FakeLock()

    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "1")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "0")
    _install_fake_async_redis(monkeypatch, FakeRedis())

    async def _run() -> None:
        async with request_gate.acquire_geocode_request_slot_async("pelias"):
            events.append("inside")

    asyncio.run(_run())
    assert events == [
        "lock:backfield:geocode:pelias:slot:0",
        "acquire",
        "inside",
        "release",
    ]


class _TicketRedis:
    """Fake Redis that records ticket reservations and slot locks in call order."""

    def __init__(self, events: list[str], delay_us: int = 0) -> None:
        self.events = events
        self.delay_us = delay_us

    def eval(self, script: str, numkeys: int, key: str, interval_us: int) -> int:
        assert "TIME" in script
        self.events.append(f"ticket:{numkeys}:{key}:{interval_us}")
        return self.delay_us

    def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> object:
        events = self.events

        class FakeLock:
            def acquire(self, *, blocking: bool) -> bool:
                events.append("slot_acquire")
                return True

            def release(self) -> None:
                events.append("slot_release")

        return FakeLock()


def _install_fake_redis(monkeypatch, client: object) -> None:
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda *_args, **_kwargs: client),
    )


class _AsyncFakeRedis:
    """Async view of a fake sync client (same recorded events and slot state)."""

    def __init__(self, sync_client: object) -> None:
        self._sync = sync_client

    async def eval(self, *args: object) -> int:
        return self._sync.eval(*args)

    def lock(self, *args: object, **kwargs: object) -> object:
        sync_lock = self._sync.lock(*args, **kwargs)

        class AsyncLock:
            async def acquire(self, *, blocking: bool) -> bool:
                return sync_lock.acquire(blocking=blocking)

            async def release(self) -> None:
                sync_lock.release()

        return AsyncLock()

    async def aclose(self) -> None:
        return None


def _install_fake_async_redis(monkeypatch, sync_client: object) -> None:
    async_client = _AsyncFakeRedis(sync_client)
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(
            from_url=lambda *_a, **_k: sync_client,
            asyncio=SimpleNamespace(from_url=lambda *_a, **_k: async_client),
        ),
    )


def test_pelias_ticket_gate_sleeps_before_taking_slot(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "1")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "10")
    _install_fake_redis(monkeypatch, _TicketRedis(events, delay_us=250_000))
    monkeypatch.setattr(
        request_gate.time, "sleep", lambda seconds: events.append(f"sleep:{seconds}")
    )

    with request_gate.acquire_geocode_request_slot("pelias"):
        events.append("inside")

    assert events == [
        "ticket:1:backfield:geocode:pelias:next_slot:100000",
        "sleep:0.25",
        "slot_acquire",
        "inside",
        "slot_release",
    ]


def test_pelias_ticket_gate_disabled_when_rps_zero(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "1")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "0")
    _install_fake_redis(monkeypatch, _TicketRedis(events, delay_us=999))

    with request_gate.acquire_geocode_request_slot("pelias"):
        pass

    assert not any(e.startswith("ticket:") for e in events)


def test_pelias_ticket_gate_fails_open_on_redis_error(monkeypatch) -> None:
    class BrokenRedis:
        def eval(self, *_args: object) -> int:
            raise RuntimeError("redis down")

    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "0")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "10")
    _install_fake_redis(monkeypatch, BrokenRedis())

    with request_gate.acquire_geocode_request_slot("pelias"):
        ran = True
    assert ran is True


def test_async_pelias_gate_sleeps_on_event_loop_then_takes_slot(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_CONCURRENT", "1")
    monkeypatch.setenv("GEOCODE_PELIAS_MAX_RPS", "4")
    _install_fake_async_redis(monkeypatch, _TicketRedis(events, delay_us=500_000))

    async def fake_sleep(seconds: float) -> None:
        events.append(f"async_sleep:{seconds}")

    monkeypatch.setattr(request_gate.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        request_gate.time, "sleep", lambda _s: events.append("blocking_sleep")
    )

    async def _run() -> None:
        async with request_gate.acquire_geocode_request_slot_async("pelias"):
            events.append("inside")

    asyncio.run(_run())

    # One ticket only (not re-taken by the sync gate), event-loop sleep, then the slot.
    assert events == [
        "ticket:1:backfield:geocode:pelias:next_slot:250000",
        "async_sleep:0.5",
        "slot_acquire",
        "inside",
        "slot_release",
    ]


class _SingleSlotRedis:
    """Fake Redis with one real, shared concurrency slot."""

    def __init__(self) -> None:
        self._held = threading.Lock()
        self.releases = 0

    def lock(self, name: str, *, timeout: int, blocking_timeout: int) -> object:
        outer = self

        class FakeLock:
            def acquire(self, *, blocking: bool) -> bool:
                return outer._held.acquire(blocking=False)

            def release(self) -> None:
                outer.releases += 1
                outer._held.release()

        return FakeLock()


def test_async_slot_waiters_do_not_starve_slot_release(monkeypatch) -> None:
    """Waiters must not park every worker thread, or slot holders can never release."""
    redis_client = _SingleSlotRedis()
    monkeypatch.setenv("GEOCODE_NOMINATIM_MAX_CONCURRENT", "1")
    _install_fake_async_redis(monkeypatch, redis_client)
    completed = 0

    async def _use_slot() -> None:
        nonlocal completed
        async with request_gate.acquire_geocode_request_slot_async("nominatim"):
            await asyncio.sleep(0.01)
        completed += 1

    async def _run() -> None:
        # Two worker threads for 20 callers: parked waiters would fill the pool and deadlock.
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=2))
        await asyncio.wait_for(asyncio.gather(*[_use_slot() for _ in range(20)]), timeout=20)

    asyncio.run(_run())
    assert completed == 20
    assert redis_client.releases == 20


def test_async_slot_is_released_when_caller_is_cancelled(monkeypatch) -> None:
    redis_client = _SingleSlotRedis()
    monkeypatch.setenv("GEOCODE_NOMINATIM_MAX_CONCURRENT", "1")
    _install_fake_async_redis(monkeypatch, redis_client)

    async def _hold_slot_forever() -> None:
        async with request_gate.acquire_geocode_request_slot_async("nominatim"):
            await asyncio.sleep(60)

    async def _run() -> None:
        task = asyncio.ensure_future(_hold_slot_forever())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.1)

    asyncio.run(_run())
    assert redis_client.releases == 1
    assert redis_client._held.acquire(blocking=False)


def test_async_gate_reuses_one_redis_client_per_event_loop(monkeypatch) -> None:
    """New connections resolve hostnames on the thread pool, so the client must be reused."""
    sync_client = _SingleSlotRedis()
    created: list[object] = []
    async_client = _AsyncFakeRedis(sync_client)

    def make_async_client(*_args: object, **_kwargs: object) -> object:
        created.append(async_client)
        return async_client

    monkeypatch.setenv("GEOCODE_NOMINATIM_MAX_CONCURRENT", "1")
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(
            from_url=lambda *_a, **_k: sync_client,
            asyncio=SimpleNamespace(from_url=make_async_client),
        ),
    )

    async def _run() -> None:
        for _ in range(5):
            async with request_gate.acquire_geocode_request_slot_async("nominatim"):
                pass

    asyncio.run(_run())
    assert len(created) == 1


def test_pelias_get_acquires_fleet_gate() -> None:
    from agate_utils.geocoding.pelias import _pelias_get

    acquired: list[str] = []

    @asynccontextmanager
    async def fake_gate(provider: str):
        acquired.append(provider)
        yield

    response = MagicMock()
    response.status_code = 200
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    async def _run() -> None:
        with patch(
            "agate_utils.geocoding.request_gate.acquire_geocode_request_slot_async",
            fake_gate,
        ):
            await _pelias_get(client, "https://example.test/v1/search", {"text": "x"})

    asyncio.run(_run())
    assert acquired == ["pelias"]


def test_nominatim_geocode_acquires_fleet_gate(monkeypatch) -> None:
    from agate_utils.geocoding.nominatim import NominatimGeocoder

    acquired: list[str] = []

    @contextmanager
    def fake_gate(provider: str, max_wait_s: float | None = None):
        acquired.append(provider)
        yield

    geocoder = NominatimGeocoder(user_agent="test")
    monkeypatch.setattr(geocoder, "_enforce_rate_limit", lambda: None)
    monkeypatch.setattr(
        geocoder,
        "_get_geocoder",
        lambda: SimpleNamespace(geocode=lambda *_a, **_k: MagicMock()),
    )
    monkeypatch.setattr(
        geocoder,
        "_location_to_result",
        lambda *_a, **_k: SimpleNamespace(ok=True),
    )
    with patch(
        "agate_utils.geocoding.nominatim.acquire_geocode_request_slot",
        fake_gate,
    ):
        assert geocoder.geocode("Chicago") is not None
    assert acquired == ["nominatim"]


def test_geocodio_search_acquires_fleet_gate(monkeypatch) -> None:
    from agate_utils.geocoding import geocodio as geocodio_mod

    acquired: list[str] = []

    @contextmanager
    def fake_gate(provider: str, max_wait_s: float | None = None):
        acquired.append(provider)
        yield

    location = MagicMock()
    location.address = "1 Main St"
    location.latitude = 41.0
    location.longitude = -87.0
    location.raw = {
        "formatted_address": "1 Main St",
        "accuracy": 1.0,
        "address_components": {},
        "location": {"lat": 41.0, "lng": -87.0},
    }

    class FakeGeocodio:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def geocode(self, _query: str) -> object:
            return location

    monkeypatch.setattr(geocodio_mod, "Geocodio", FakeGeocodio)
    with patch(
        "agate_utils.geocoding.geocodio.acquire_geocode_request_slot",
        fake_gate,
    ):
        result = geocodio_mod.geocode_search("Chicago", api_key="k")
    assert result is not None
    assert acquired == ["geocodio"]
