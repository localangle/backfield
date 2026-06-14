"""GET /public/v1/projects/{project_slug}/locations/{location_id}/connections."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.connections import (
    PublicConnectionOut,
    list_public_entity_connections,
)
from backfield_entities.public.locations import get_public_location
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.locations.helpers import (
    parse_location_id,
    resolve_public_locations_scope,
)

router = APIRouter()


class PublicLocationConnectionsOut(BaseModel):
    location_id: str
    connections: list[PublicConnectionOut]


@router.get("/{location_id}/connections", response_model=PublicLocationConnectionsOut)
def list_project_location_connections(
    location_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicLocationConnectionsOut:
    """Return Stylebook connections involving this canonical location."""
    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    parsed_id = parse_location_id(location_id)
    location = get_public_location(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=parsed_id,
    )
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    connections = list_public_entity_connections(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type="location",
        entity_id=parsed_id,
    )
    return PublicLocationConnectionsOut(location_id=location.id, connections=connections)
