"""Collector and Celery publish-timestamp unit tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from backfield_observability.celery_publish import (
    PUBLISH_TIMESTAMP_HEADER,
    stamp_task_publish_headers,
)
from worker.metrics_collector import _decode_publish_timestamp, collect_queue_metrics


def test_stamp_task_publish_headers_sets_iso_timestamp() -> None:
    headers: dict[str, object] = {}
    stamp_task_publish_headers(headers=headers)
    assert PUBLISH_TIMESTAMP_HEADER in headers
    datetime.fromisoformat(str(headers[PUBLISH_TIMESTAMP_HEADER]))


def test_collect_queue_metrics_omits_age_when_header_missing() -> None:
    client = MagicMock()
    client.llen.return_value = 2
    client.lindex.return_value = json.dumps({"headers": {}}).encode()
    depth, age = collect_queue_metrics(redis_client=client, queue="agate")
    assert depth == 2
    assert age is None


def test_collect_queue_metrics_computes_age_from_header() -> None:
    published = datetime.now(UTC) - timedelta(seconds=42)
    payload = {"headers": {PUBLISH_TIMESTAMP_HEADER: published.isoformat()}}
    client = MagicMock()
    client.llen.return_value = 1
    client.lindex.return_value = json.dumps(payload).encode()
    depth, age = collect_queue_metrics(redis_client=client, queue="agate")
    assert depth == 1
    assert age is not None
    assert 40 <= age <= 50


def test_decode_publish_timestamp_accepts_iso() -> None:
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    raw = json.dumps({"headers": {PUBLISH_TIMESTAMP_HEADER: stamp.isoformat()}})
    assert _decode_publish_timestamp(raw) == stamp
