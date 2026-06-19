"""GET /public/v1/projects/{project_slug}/people/{person_id}/articles."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.articles import PublicArticleOut
from backfield_entities.public.people import get_public_person, list_public_person_articles
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


class PublicPersonArticlesOut(BaseModel):
    person_id: str
    label: str
    items: list[PublicArticleOut]
    pagination: PaginationOut


@router.get("/{person_id}/articles", response_model=PublicPersonArticlesOut)
def list_project_person_articles(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    nature: str | None = Query(
        None,
        description="Filter to articles with a mention of this editorial nature",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_preview: bool = Query(
        False,
        description="Include a short text preview (max 280 characters) per article",
    ),
) -> PublicPersonArticlesOut:
    """Return paginated articles mentioning a canonical person in this project."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    parsed_id = parse_person_id(person_id)
    result = list_public_person_articles(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
        nature=nature,
        limit=limit,
        offset=offset,
        include_preview=include_preview,
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
    return PublicPersonArticlesOut(
        person_id=person.id,
        label=person.label,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
