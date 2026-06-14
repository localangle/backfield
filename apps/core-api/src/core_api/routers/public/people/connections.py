"""GET /public/v1/projects/{project_slug}/people/{person_id}/connections."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.connections import (
    PublicConnectionOut,
    list_public_entity_connections,
)
from backfield_entities.public.people import get_public_person
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.people.helpers import parse_person_id, resolve_public_people_scope

router = APIRouter()


class PublicPersonConnectionsOut(BaseModel):
    person_id: str
    connections: list[PublicConnectionOut]


@router.get("/{person_id}/connections", response_model=PublicPersonConnectionsOut)
def list_project_person_connections(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicPersonConnectionsOut:
    """Return Stylebook connections involving this canonical person."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    parsed_id = parse_person_id(person_id)
    person = get_public_person(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
    )
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    connections = list_public_entity_connections(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type="person",
        entity_id=parsed_id,
    )
    return PublicPersonConnectionsOut(person_id=person.id, connections=connections)
