"""Text helpers for PostgreSQL string columns."""

from __future__ import annotations


def strip_nul_bytes(value: str) -> str:
    """Remove NUL (0x00) bytes; PostgreSQL ``text`` / ``varchar`` reject them."""
    if "\x00" not in value:
        return value
    return value.replace("\x00", "")


def strip_nul_bytes_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return strip_nul_bytes(value)
