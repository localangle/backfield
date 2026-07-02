"""Shared normalization for user-facing editorial prose fields."""

from __future__ import annotations


def normalize_editorial_prose(value: str | None) -> str | None:
    """Capitalize the first character for display labels; leave the rest unchanged."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[0].upper() + trimmed[1:]
