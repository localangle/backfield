"""Helpers for chunked, parallel S3 batch intake.

``execute_s3_batch_setup`` loads a bucket prefix in chunks so items appear in the run (and start
running) while the rest of the listing is still being read. This module holds the parts that do
not need the database or Celery: reading objects in parallel, chunking, the ramp-up schedule, and
timing totals.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar

from agate_runtime.s3_batch import S3ObjectListing

logger = logging.getLogger(__name__)

_DEFAULT_INTAKE_CHUNK_SIZE = 50
_DEFAULT_FETCH_WORKERS = 16
_DEFAULT_RAMP_SECONDS = 60.0

_T = TypeVar("_T")


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def intake_chunk_size() -> int:
    """Objects read, committed, and queued per intake step (``S3_BATCH_INTAKE_CHUNK_SIZE``)."""
    return _positive_int_env("S3_BATCH_INTAKE_CHUNK_SIZE", _DEFAULT_INTAKE_CHUNK_SIZE)


def fetch_worker_count() -> int:
    """Parallel S3 reads per intake chunk (``S3_BATCH_FETCH_WORKERS``)."""
    return _positive_int_env("S3_BATCH_FETCH_WORKERS", _DEFAULT_FETCH_WORKERS)


def ramp_seconds() -> float:
    """Seconds over which the first in-flight window is started (0 = start all at once)."""
    raw = os.getenv("S3_BATCH_RAMP_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_RAMP_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_RAMP_SECONDS


def chunked(items: Sequence[_T], size: int) -> Iterator[Sequence[_T]]:
    """Yield consecutive slices of ``items`` with at most ``size`` entries."""
    step = max(1, size)
    for start in range(0, len(items), step):
        yield items[start : start + step]


@dataclass(frozen=True)
class FetchedObject:
    """One S3 object read: its bytes and version, or the error that stopped the read."""

    listing: S3ObjectListing
    raw_bytes: bytes | None = None
    version_id: str | None = None
    error: Exception | None = None


def fetch_object(s3_client: Any, *, bucket: str, listing: S3ObjectListing) -> FetchedObject:
    """Read one object; read failures are returned, not raised."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=listing.key)
        raw_bytes = response["Body"].read()
        version_id = response.get("VersionId")
        return FetchedObject(
            listing=listing,
            raw_bytes=raw_bytes,
            version_id=str(version_id) if version_id is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — callers classify read failures as skipped
        return FetchedObject(listing=listing, error=exc)


def fetch_objects(
    s3_client: Any,
    *,
    bucket: str,
    listings: Sequence[S3ObjectListing],
    workers: int,
) -> dict[str, FetchedObject]:
    """Read ``listings`` in parallel; returns results keyed by object key."""
    if not listings:
        return {}
    if workers <= 1 or len(listings) == 1:
        return {
            listing.key: fetch_object(s3_client, bucket=bucket, listing=listing)
            for listing in listings
        }
    with ThreadPoolExecutor(max_workers=min(workers, len(listings))) as pool:
        fetched = pool.map(
            lambda listing: fetch_object(s3_client, bucket=bucket, listing=listing),
            listings,
        )
        return {item.listing.key: item for item in fetched}


class IntakeRamp:
    """Spreads the first in-flight window over ``ramp_s`` seconds instead of starting it at once.

    Items that all start together also reach the same slow stages (database persist, provider
    calls) together. Item ``n`` of the first ``window`` starts ``n / window * ramp_s`` seconds
    after intake began; later items (refills) start immediately.
    """

    def __init__(self, *, window: int, ramp_s: float) -> None:
        self._window = max(1, window)
        self._ramp_s = max(0.0, ramp_s)
        self._started_at = time.monotonic()
        self._scheduled = 0

    def next_countdown_s(self) -> int:
        """Delay in whole seconds before the next item should start."""
        index = self._scheduled
        self._scheduled += 1
        if self._ramp_s <= 0 or index >= self._window:
            return 0
        target_s = index / self._window * self._ramp_s
        return max(0, round(target_s - (time.monotonic() - self._started_at)))


@dataclass
class IntakeTiming:
    """Seconds spent per intake phase; logged once so slow stages are visible."""

    listing_s: float = 0.0
    fetch_s: float = 0.0
    database_s: float = 0.0
    dispatch_s: float = 0.0
    chunks: int = 0

    def log(self, *, run_id: str, items: int, objects: int) -> None:
        logger.info(
            "s3_batch_intake_timing run_id=%s objects=%d items=%d chunks=%d "
            "listing_s=%.1f fetch_s=%.1f database_s=%.1f dispatch_s=%.1f",
            run_id,
            objects,
            items,
            self.chunks,
            self.listing_s,
            self.fetch_s,
            self.database_s,
            self.dispatch_s,
        )
