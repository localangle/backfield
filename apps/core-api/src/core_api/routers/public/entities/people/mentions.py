"""GET /public/v1/projects/{project_slug}/people/{person_id}/mentions."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.people import (
    PublicPersonMentionOut,
    get_public_person,
    list_public_person_mentions,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.people.helpers import (
    parse_person_id,
    resolve_public_people_scope,
)
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicPersonMentionsOut(BaseModel):
    person_id: str
    label: str
    items: list[PublicPersonMentionOut]
    pagination: PaginationOut


@router.get("/{person_id}/mentions", response_model=PublicPersonMentionsOut)
def list_project_person_mentions(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    sort: Literal["article", "created_at"] = Query("created_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicPersonMentionsOut:
    """Return paginated mention evidence for a canonical person in this project."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    parsed_id = parse_person_id(person_id)
    result = list_public_person_mentions(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
        limit=limit,
        offset=offset,
        sort=sort,
        sort_direction=sort_direction,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    items, total = result
    person = get_public_person(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
    )
    assert person is not None
    return PublicPersonMentionsOut(
        person_id=person.id,
        label=person.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
