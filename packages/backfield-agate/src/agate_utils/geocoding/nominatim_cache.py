"""Fleet-wide cache of raw Nominatim search results.

Many articles in one batch name the same rivers, lakes, and regions, and all of them queue behind
the one-at-a-time Nominatim gate. A short-lived Redis copy of each successful answer lets every
worker after the first reuse it instead of waiting for the gate and the public server. Only
non-empty answers are stored, so a miss or an outage is never remembered. Fails open without Redis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from agate_utils.geocoding.request_gate import geocode_redis_client

logger = logging.getLogger(__name__)

_DEFAULT_TTL_S = 6 * 60 * 60


def nominatim_search_cache_ttl_s() -> int:
    """Seconds a search answer is reused (``NOMINATIM_SEARCH_CACHE_TTL_S``; 0 disables)."""
    raw = os.getenv("NOMINATIM_SEARCH_CACHE_TTL_S", str(_DEFAULT_TTL_S))
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return _DEFAULT_TTL_S


def search_cache_key(params: dict[str, str]) -> str:
    """Stable key for one search request (query text plus every option that shapes the answer)."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"backfield:geocode:nominatim:search:{digest}"


def get_cached_search(key: str) -> list[dict[str, Any]] | None:
    """Return a cached answer, or ``None`` on a miss, a disabled cache, or any Redis problem."""
    if nominatim_search_cache_ttl_s() <= 0:
        return None
    client = geocode_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(key)  # type: ignore[attr-defined]
        if raw is None:
            return None
        results = json.loads(raw)
    except Exception:
        logger.debug("Nominatim search cache read failed", exc_info=True)
        return None
    return results if isinstance(results, list) else None


def store_cached_search(key: str, results: list[dict[str, Any]]) -> None:
    """Remember a non-empty answer for ``NOMINATIM_SEARCH_CACHE_TTL_S`` seconds."""
    ttl_s = nominatim_search_cache_ttl_s()
    if ttl_s <= 0 or not results:
        return
    client = geocode_redis_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(results), ex=ttl_s)  # type: ignore[attr-defined]
    except Exception:
        logger.debug("Nominatim search cache write failed", exc_info=True)
