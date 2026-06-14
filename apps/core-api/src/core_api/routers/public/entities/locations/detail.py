"""GET /public/v1/projects/{project_slug}/locations/{location_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.locations import PublicLocationOut, get_public_location
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.locations.helpers import (
    parse_location_id,
    resolve_public_locations_scope,
)

router = APIRouter()


@router.get("/{location_id}", response_model=PublicLocationOut)
def get_project_location(
    location_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicLocationOut:
    """Return one canonical location by UUID."""
    stylebook_id, project_id = resolve_public_locations_scope(session, project)
    location = get_public_location(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=parse_location_id(location_id),
    )
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location
