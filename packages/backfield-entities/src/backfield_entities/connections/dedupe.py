"""Null-safe helpers for ``stylebook_connections`` edge identity."""

from __future__ import annotations

from backfield_db import StylebookConnection
from sqlalchemy import func


def normalize_connection_nature(nature: str | None) -> str | None:
    if nature is None:
        return None
    stripped = nature.strip().lower()
    return stripped or None


def normalize_connection_description(description: str | None) -> str | None:
    if description is None:
        return None
    stripped = description.strip()
    return stripped or None


def connection_nature_coalesced(column: object = StylebookConnection.nature) -> object:
    return func.coalesce(column, "")
