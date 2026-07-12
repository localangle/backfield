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


def connection_edge_key(
    *,
    project_id: int,
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
    nature: str | None,
    description: str | None,
) -> tuple[int, str, str, str, str, str, str]:
    return (
        int(project_id),
        from_entity_type.strip().lower(),
        str(from_entity_id),
        to_entity_type.strip().lower(),
        str(to_entity_id),
        normalize_connection_nature(nature) or "",
        normalize_connection_description(description) or "",
    )


def connection_nature_coalesced(column: object = StylebookConnection.nature) -> object:
    return func.coalesce(column, "")


def connection_description_coalesced(column: object = StylebookConnection.description) -> object:
    return func.coalesce(column, "")
