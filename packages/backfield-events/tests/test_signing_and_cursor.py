"""Signature and cursor contract tests for backfield-events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backfield_events.cursor import (
    CursorError,
    CursorExpiredError,
    decode_event_cursor,
    encode_event_cursor,
)
from backfield_events.signing import (
    build_signature_headers,
    sign_webhook_payload,
    verify_webhook_signature,
)


def test_signature_covers_timestamp_and_body() -> None:
    signature = sign_webhook_payload(secret="topsecret", timestamp="1700000000", body=b'{"a":1}')
    assert signature.startswith("v1=")
    assert verify_webhook_signature(
        secret="topsecret",
        timestamp="1700000000",
        body=b'{"a":1}',
        signature=signature,
    )
    # Changing the timestamp or body invalidates the signature.
    assert not verify_webhook_signature(
        secret="topsecret",
        timestamp="1700000001",
        body=b'{"a":1}',
        signature=signature,
    )
    assert not verify_webhook_signature(
        secret="topsecret",
        timestamp="1700000000",
        body=b'{"a":2}',
        signature=signature,
    )


def test_signature_headers_are_stable_and_complete() -> None:
    headers = build_signature_headers(
        secret="topsecret",
        timestamp="1700000000",
        body=b"{}",
        event_uuid="evt-uuid",
        delivery_id="dl-1",
        event_type="agate.run.completed",
    )
    assert headers["Backfield-Event-Id"] == "evt-uuid"
    assert headers["Backfield-Delivery-Id"] == "dl-1"
    assert headers["Backfield-Event-Type"] == "agate.run.completed"
    assert headers["Backfield-Timestamp"] == "1700000000"
    assert headers["Backfield-Signature"].startswith("v1=")


def test_cursor_roundtrip() -> None:
    now = datetime.now(UTC)
    cursor = encode_event_cursor(sequence=1234, created_at=now)
    assert decode_event_cursor(cursor) == 1234


def test_cursor_rejects_garbage() -> None:
    with pytest.raises(CursorError):
        decode_event_cursor("not-a-cursor!!!")


def test_cursor_beyond_retention_window_expires() -> None:
    old = datetime.now(UTC) - timedelta(days=91)
    cursor = encode_event_cursor(sequence=5, created_at=old)
    with pytest.raises(CursorExpiredError):
        decode_event_cursor(cursor)
