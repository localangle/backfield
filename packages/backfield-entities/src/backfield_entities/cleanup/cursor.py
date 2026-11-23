"""Opaque pagination cursors for cleanup reads.

A cursor is the URL-safe base64 encoding of a small JSON object. Callers must treat it as opaque:
the shape can change between contract versions.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

CursorT = TypeVar("CursorT", bound=BaseModel)


class InvalidCursorError(ValueError):
    """Raised when a cursor cannot be decoded; routes map this to a 400."""


def encode_cursor(payload: BaseModel) -> str:
    """Encode a cursor payload as an opaque string."""
    raw = payload.model_dump_json().encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, model: type[CursorT]) -> CursorT:
    """Decode a cursor string into ``model`` or raise ``InvalidCursorError``."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return model.model_validate(json.loads(raw))
    except (binascii.Error, UnicodeError, ValueError, ValidationError) as exc:
        raise InvalidCursorError("Invalid cursor.") from exc
