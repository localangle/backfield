"""GET /public/v1/projects/{project_slug}/people/types."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.stylebook_scope import list_public_person_type_values
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.people.helpers import resolve_public_people_scope

router = APIRouter()


class PublicPersonTypesOut(BaseModel):
    types: list[str]


@router.get("/types", response_model=PublicPersonTypesOut)
def list_project_person_types(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicPersonTypesOut:
    """Return distinct person type values for filter dropdowns."""
    stylebook_id, _project_id = resolve_public_people_scope(session, project)
    types = list_public_person_type_values(session, stylebook_id=stylebook_id)
    return PublicPersonTypesOut(types=types)
