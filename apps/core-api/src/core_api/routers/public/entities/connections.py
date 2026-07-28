"""Shared response construction for public entity connection routes."""

from __future__ import annotations

from backfield_entities.public.connections import (
    PublicConnectionEntityType,
    PublicConnectionOut,
    list_public_entity_connections,
)
from sqlmodel import Session

from core_api.routers.public.schemas import PaginatedResponse, PaginationOut


def public_entity_connections_response(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    entity_type: PublicConnectionEntityType,
    entity_id: str,
    to_entity_type: PublicConnectionEntityType | None,
    nature: str | None,
    limit: int,
    offset: int,
) -> PaginatedResponse[PublicConnectionOut]:
    """List, filter, and page one canonical entity's connections."""
    items, total = list_public_entity_connections(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type=entity_type,
        entity_id=entity_id,
        to_entity_type=to_entity_type,
        nature=nature,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
