"""Fleet-wide Redis gates for outbound geocoder HTTP calls.

Caps concurrent Pelias / Nominatim / Geocodio / Overpass requests across Celery workers so
per-article ``GEOCODE_MAX_CONCURRENT`` cannot stampede provider limits. Pelias
also gets a first-come, first-served ticket gate aligned to Geocode Earth's
~10 req/s cap: each request reserves the next free time slot (spaced
``1 / GEOCODE_PELIAS_MAX_RPS`` apart) in Redis and sleeps until it arrives, then takes a
concurrency slot. Fail-open when Redis is unavailable (same posture as DBOutput persist slots).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import weakref
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Literal

GeocodeProvider = Literal["pelias", "nominatim", "geocodio", "overpass"]

logger = logging.getLogger(__name__)

_DEFAULT_MAX: dict[GeocodeProvider, int] = {
    # Align with ~10 req/s Geocode Earth cap; RPS limiter is the hard throttle.
    "pelias": 10,
    "nominatim": 1,
    "geocodio": 8,
    # Public Overpass servers answer "at capacity" quickly; keep the whole fleet small.
    "overpass": 3,
}

_ENV_MAX: dict[GeocodeProvider, str] = {
    "pelias": "GEOCODE_PELIAS_MAX_CONCURRENT",
    "nominatim": "GEOCODE_NOMINATIM_MAX_CONCURRENT",
    "geocodio": "GEOCODE_GEOCODIO_MAX_CONCURRENT",
    "overpass": "GEOCODE_OVERPASS_MAX_CONCURRENT",
}


class GateWaitTimeout(TimeoutError):
    """Raised when a gate caller gave up waiting for a concurrency slot."""


def geocode_request_gate_ttl_s() -> int:
    raw = os.getenv("GEOCODE_REQUEST_GATE_TTL_S", "120")
    try:
        return max(1, int(raw))
    except ValueError:
        return 120


def geocode_provider_max_concurrent(provider: GeocodeProvider) -> int:
    """Return max concurrent requests for ``provider`` (0 disables the concurrency gate)."""
    env_name = _ENV_MAX[provider]
    raw = os.getenv(env_name)
    if raw is None or raw.strip() == "":
        return _DEFAULT_MAX[provider]
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return _DEFAULT_MAX[provider]


def geocode_pelias_max_rps() -> int:
    """Return Pelias max requests per second (0 disables the ticket gate)."""
    raw = os.getenv("GEOCODE_PELIAS_MAX_RPS", "10")
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return 10


_PELIAS_TICKET_KEY = "backfield:geocode:pelias:next_slot"

# Atomic ticket reservation (GCRA): read the shared clock, hand out the next free time slot,
# and return how long the caller must wait for it. All times are in microseconds.
# KEYS[1] = next-free-slot key; ARGV[1] = spacing between slots.
_PELIAS_TICKET_LUA = """
local t = redis.call('TIME')
local now = t[1] * 1000000 + t[2]
local interval = tonumber(ARGV[1])
local stored = redis.call('GET', KEYS[1])
local next_free = 0
if stored then next_free = tonumber(stored) end
local start = now
if next_free > now then start = next_free end
local new_next = start + interval
redis.call('SET', KEYS[1], string.format('%.0f', new_next), 'PX', math.ceil((new_next - now) / 1000) + 1000)
return start - now
"""


def _slot_key(provider: GeocodeProvider, slot: int) -> str:
    return f"backfield:geocode:{provider}:slot:{slot}"


def _connect_gate_redis() -> object | None:
    """Return a Redis client for the gates, or ``None`` when Redis cannot be configured."""
    try:
        import redis

        return redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception:
        return None


def _reserve_pelias_ticket_delay_s(client: object) -> float:
    """Reserve the next Pelias time slot and return seconds to wait before using it."""
    max_rps = geocode_pelias_max_rps()
    if max_rps <= 0:
        return 0.0
    # redis-py client; typed as object to avoid hard import at module load.
    delay_us = int(
        client.eval(  # type: ignore[attr-defined]
            _PELIAS_TICKET_LUA, 1, _PELIAS_TICKET_KEY, _pelias_ticket_interval_us()
        )
    )
    delay_s = max(0, delay_us) / 1_000_000.0
    _log_pelias_ticket_wait(delay_s)
    return delay_s


# One asyncio Redis client per running event loop. A new connection resolves the Redis hostname
# through the loop's default thread pool, which can be busy with blocking work; reusing the
# client's pooled connections keeps the gate off that pool after warm-up.
_ASYNC_GATE_CLIENTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, object] = (
    weakref.WeakKeyDictionary()
)


def _connect_gate_redis_async() -> object | None:
    """Return the event loop's shared asyncio Redis client, or ``None`` when unavailable."""
    loop = asyncio.get_running_loop()
    client = _ASYNC_GATE_CLIENTS.get(loop)
    if client is not None:
        return client
    try:
        from redis import asyncio as redis_asyncio

        client = redis_asyncio.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            # Generous connect timeout: failing open here silently drops the rate cap.
            socket_connect_timeout=10,
            socket_timeout=5,
        )
    except Exception:
        return None
    _ASYNC_GATE_CLIENTS[loop] = client
    return client


def _pelias_ticket_interval_us() -> int:
    return max(1, 1_000_000 // geocode_pelias_max_rps())


def _log_pelias_ticket_wait(delay_s: float) -> None:
    if delay_s * 1000.0 >= 50.0:
        logger.info("geocode_pelias_ticket_wait wait_ms=%.1f", delay_s * 1000.0)


async def _reserve_pelias_ticket_delay_async_s(client: object) -> float:
    """Async twin of :func:`_reserve_pelias_ticket_delay_s`; fails open (no wait)."""
    try:
        delay_us = int(
            await client.eval(  # type: ignore[attr-defined]
                _PELIAS_TICKET_LUA, 1, _PELIAS_TICKET_KEY, _pelias_ticket_interval_us()
            )
        )
    except Exception:
        logger.warning("Pelias ticket gate unavailable; continuing without rate cap", exc_info=True)
        return 0.0
    delay_s = max(0, delay_us) / 1_000_000.0
    _log_pelias_ticket_wait(delay_s)
    return delay_s


def _try_acquire_any_slot(
    client: object,
    provider: GeocodeProvider,
    max_concurrent: int,
) -> object | None:
    """Try each concurrency slot once (non-blocking); return the held lock or ``None``."""
    ttl_s = geocode_request_gate_ttl_s()
    for slot in range(max_concurrent):
        candidate = client.lock(  # type: ignore[attr-defined]
            _slot_key(provider, slot),
            timeout=ttl_s,
            blocking_timeout=0,
        )
        if candidate.acquire(blocking=False):
            return candidate
    return None


def _release_slot_lock(lock: object, provider: GeocodeProvider) -> None:
    try:
        lock.release()  # type: ignore[attr-defined]
    except Exception:
        logger.debug(
            "Geocode request gate lock release failed for %s",
            provider,
            exc_info=True,
        )


@contextmanager
def acquire_geocode_request_slot(
    provider: GeocodeProvider, *, max_wait_s: float | None = None
) -> Iterator[None]:
    """Block until the Pelias ticket time and a provider concurrency slot allow an HTTP call.

    ``max_wait_s`` bounds the wait for a concurrency slot; ``GateWaitTimeout`` is raised
    (not swallowed by the fail-open handling) when it elapses.

    The Pelias ticket is taken (and slept on) before the concurrency slot so waiting callers
    never hold a slot. Async callers use :func:`acquire_geocode_request_slot_async`.
    """
    max_concurrent = geocode_provider_max_concurrent(provider)
    need_ticket = provider == "pelias" and geocode_pelias_max_rps() > 0
    if max_concurrent <= 0 and not need_ticket:
        yield
        return

    client = _connect_gate_redis()
    if client is None:
        logger.warning(
            "Geocode request gate unavailable for %s; continuing without concurrency cap",
            provider,
        )
        yield
        return

    lock = None
    wait_started = time.perf_counter()
    try:
        if need_ticket:
            time.sleep(_reserve_pelias_ticket_delay_s(client))
        if max_concurrent > 0:
            while lock is None:
                lock = _try_acquire_any_slot(client, provider, max_concurrent)
                if lock is None:
                    if max_wait_s is not None and time.perf_counter() - wait_started >= max_wait_s:
                        raise GateWaitTimeout(
                            f"No {provider} request slot free after {max_wait_s:.1f}s"
                        )
                    time.sleep(0.05)
    except GateWaitTimeout:
        raise
    except Exception:
        logger.warning(
            "Geocode request gate acquire failed for %s; continuing without concurrency cap",
            provider,
            exc_info=True,
        )
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass
        yield
        return

    wait_ms = (time.perf_counter() - wait_started) * 1000.0
    if wait_ms >= 50.0:
        logger.info(
            "geocode_request_gate_acquired provider=%s wait_ms=%.1f",
            provider,
            wait_ms,
        )

    hold_started = time.perf_counter()
    try:
        yield
    finally:
        hold_ms = (time.perf_counter() - hold_started) * 1000.0
        if hold_ms >= 1000.0:
            logger.info(
                "geocode_request_gate_released provider=%s hold_ms=%.1f",
                provider,
                hold_ms,
            )
        if lock is not None:
            _release_slot_lock(lock, provider)


async def _try_acquire_any_slot_async(
    client: object,
    provider: GeocodeProvider,
    max_concurrent: int,
) -> object | None:
    """Try each concurrency slot once (non-blocking); return the held lock or ``None``."""
    ttl_s = geocode_request_gate_ttl_s()
    for slot in range(max_concurrent):
        candidate = client.lock(  # type: ignore[attr-defined]
            _slot_key(provider, slot),
            timeout=ttl_s,
            blocking_timeout=0,
        )
        if await candidate.acquire(blocking=False):
            return candidate
    return None


async def _release_slot_lock_async(lock: object, provider: GeocodeProvider) -> None:
    try:
        await lock.release()  # type: ignore[attr-defined]
    except Exception:
        logger.debug(
            "Geocode request gate lock release failed for %s",
            provider,
            exc_info=True,
        )


async def _acquire_slot_lock_async(
    client: object,
    provider: GeocodeProvider,
    max_concurrent: int,
) -> object:
    """Wait on the event loop for a concurrency slot.

    The async gate never uses worker threads: callers also run blocking work (language-model
    calls, database lookups) in the default thread pool, and a pool full of that work would
    leave no thread to take or release slots, so slots would stay held until their lock expiry.
    """
    while True:
        attempt = asyncio.ensure_future(
            _try_acquire_any_slot_async(client, provider, max_concurrent)
        )
        try:
            lock = await asyncio.shield(attempt)
        except asyncio.CancelledError:
            # The attempt may still win a slot after we were cancelled; hand it back.
            attempt.add_done_callback(lambda done: _release_orphaned_attempt(done, provider))
            raise
        if lock is not None:
            return lock
        await asyncio.sleep(random.uniform(0.05, 0.15))


def _release_orphaned_attempt(
    done: asyncio.Future[object | None], provider: GeocodeProvider
) -> None:
    if done.cancelled() or done.exception() is not None:
        return
    lock = done.result()
    if lock is not None:
        asyncio.ensure_future(_release_slot_lock_async(lock, provider))


@asynccontextmanager
async def acquire_geocode_request_slot_async(
    provider: GeocodeProvider,
) -> AsyncIterator[None]:
    """Async gate for httpx call sites: Pelias ticket sleep, then a concurrency slot.

    Everything here waits on the event loop (Redis asyncio client plus ``asyncio.sleep``);
    no worker thread is used. Fails open when Redis is unavailable.
    """
    need_ticket = provider == "pelias" and geocode_pelias_max_rps() > 0
    max_concurrent = geocode_provider_max_concurrent(provider)
    if max_concurrent <= 0 and not need_ticket:
        yield
        return

    client = _connect_gate_redis_async()
    if client is None:
        logger.warning(
            "Geocode request gate unavailable for %s; continuing without concurrency cap",
            provider,
        )
        yield
        return

    lock = None
    wait_started = time.perf_counter()
    try:
        if need_ticket:
            await asyncio.sleep(await _reserve_pelias_ticket_delay_async_s(client))
        if max_concurrent > 0:
            lock = await _acquire_slot_lock_async(client, provider, max_concurrent)
    except Exception:
        logger.warning(
            "Geocode request gate acquire failed for %s; continuing without concurrency cap",
            provider,
            exc_info=True,
        )
        lock = None
        yield
        return

    wait_ms = (time.perf_counter() - wait_started) * 1000.0
    if wait_ms >= 50.0:
        logger.info(
            "geocode_request_gate_acquired provider=%s wait_ms=%.1f",
            provider,
            wait_ms,
        )

    hold_started = time.perf_counter()
    try:
        yield
    finally:
        hold_ms = (time.perf_counter() - hold_started) * 1000.0
        if hold_ms >= 1000.0:
            logger.info(
                "geocode_request_gate_released provider=%s hold_ms=%.1f",
                provider,
                hold_ms,
            )
        if lock is not None:
            # Shielded so a cancelled caller still frees its slot.
            await asyncio.shield(_release_slot_lock_async(lock, provider))


########## OVERPASS COOL-DOWN ##########

_OVERPASS_COOLDOWN_KEY = "backfield:geocode:overpass:cooldown"


def overpass_cooldown_s() -> int:
    """Seconds the whole fleet skips Overpass after it fails (0 disables the cool-down)."""
    raw = os.getenv("OVERPASS_COOLDOWN_S", "60")
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return 60


def overpass_cooldown_active() -> bool:
    """True while a recent Overpass failure asks every worker to skip Overpass. Fails open."""
    if overpass_cooldown_s() <= 0:
        return False
    client = _connect_gate_redis()
    if client is None:
        return False
    try:
        return bool(client.exists(_OVERPASS_COOLDOWN_KEY))  # type: ignore[attr-defined]
    except Exception:
        logger.debug("Overpass cool-down check failed", exc_info=True)
        return False


def start_overpass_cooldown(reason: str) -> None:
    """Ask every worker to skip Overpass for ``OVERPASS_COOLDOWN_S`` seconds."""
    cooldown_s = overpass_cooldown_s()
    if cooldown_s <= 0:
        return
    client = _connect_gate_redis()
    if client is None:
        return
    try:
        client.set(_OVERPASS_COOLDOWN_KEY, reason[:200], ex=cooldown_s)  # type: ignore[attr-defined]
        logger.warning("overpass_cooldown_started seconds=%d reason=%s", cooldown_s, reason)
    except Exception:
        logger.debug("Overpass cool-down start failed", exc_info=True)
