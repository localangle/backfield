"""Opaque forward cursors for the public event feed."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta

_CURSOR_VERSION = "v1"

EVENT_RETENTION_DAYS = 90


class CursorError(ValueError):
    """The cursor is malformed and cannot be decoded."""


class CursorExpiredError(ValueError):
    """The cursor predates the event retention window; events may have been purged."""


def encode_event_cursor(*, sequence: int, created_at: datetime) -> str:
    """Encode the last-seen event sequence plus its creation time."""
    epoch = int(created_at.timestamp())
    raw = f"{_CURSOR_VERSION}:{sequence}:{epoch}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_event_cursor(cursor: str, *, now: datetime | None = None) -> int:
    """Return the last-seen sequence, raising when malformed or beyond retention."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise CursorError("Malformed event cursor") from e

    parts = raw.split(":")
    if len(parts) != 3 or parts[0] != _CURSOR_VERSION:
        raise CursorError("Malformed event cursor")
    try:
        sequence = int(parts[1])
        epoch = int(parts[2])
    except ValueError as e:
        raise CursorError("Malformed event cursor") from e

    current = now or datetime.now(UTC)
    cursor_time = datetime.fromtimestamp(epoch, tz=UTC)
    if cursor_time < current - timedelta(days=EVENT_RETENTION_DAYS):
        raise CursorExpiredError(
            "Cursor predates the event retention window; restart without a cursor"
        )
    return sequence
