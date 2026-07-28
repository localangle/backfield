"""GET /public/v1/projects/{project_slug}/people/{person_id}/connections."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.connections import (
    PublicConnectionEntityType,
    PublicConnectionOut,
)
from backfield_entities.public.people import get_public_person
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.connections import public_entity_connections_response
from core_api.routers.public.entities.people.helpers import (
    parse_person_id,
    resolve_public_people_scope,
)
from core_api.routers.public.schemas import PaginatedResponse

router = APIRouter()


@router.get(
    "/{person_id}/connections",
    response_model=PaginatedResponse[PublicConnectionOut],
)
def list_project_person_connections(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    to_entity_type: PublicConnectionEntityType | None = Query(None),
    nature: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicConnectionOut]:
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
    return public_entity_connections_response(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type="person",
        entity_id=parsed_id,
        to_entity_type=to_entity_type,
        nature=nature,
        limit=limit,
        offset=offset,
    )
