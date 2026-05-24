"""Small shared helpers for substrate persistence (whitespace, time, hashes, dates)."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from typing import Any

_WS_RE = re.compile(r"\s+")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_name(value: str) -> str:
    cleaned = _WS_RE.sub(" ", value.strip()).lower()
    return cleaned


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        # Accept YYYY-MM-DD or full ISO timestamps.
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None
