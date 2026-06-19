"""GET /public/v1/projects/{project_slug}/people/{person_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.people import PublicPersonOut, get_public_person
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.people.helpers import (
    parse_person_id,
    resolve_public_people_scope,
)

router = APIRouter()


@router.get("/{person_id}", response_model=PublicPersonOut)
def get_project_person(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicPersonOut:
    """Return one canonical person by UUID."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    person = get_public_person(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parse_person_id(person_id),
    )
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return person
