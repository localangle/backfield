"""GET /public/v1/projects/{project_slug}/people/{person_id}/mentions."""

from __future__ import annotations

from typing import Literal

from backfield_db import BackfieldProject
from backfield_entities.public.mention_timeline import (
    PublicEntityMentionTimelineItemOut,
    list_public_person_mention_timeline,
)
from backfield_entities.public.people import (
    PublicPersonMentionOut,
    get_public_person,
    list_public_person_mentions,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import (
    META_PARAM_DESCRIPTION,
    parse_meta_clauses,
    parse_optional_date,
)
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.mention_helpers import (
    build_entity_mention_list_params,
    build_entity_mention_timeline_params,
)
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


class PublicPersonMentionTimelineOut(BaseModel):
    person_id: str
    label: str
    items: list[PublicEntityMentionTimelineItemOut]


@router.get("/{person_id}/mentions/timeline", response_model=PublicPersonMentionTimelineOut)
def list_project_person_mention_timeline(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
) -> PublicPersonMentionTimelineOut:
    """Return mention counts grouped by article publication date for one canonical person."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    parsed_id = parse_person_id(person_id)
    params = build_entity_mention_timeline_params(
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        quotes_only=quote is True,
    )
    items = list_public_person_mention_timeline(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
        params=params,
    )
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    person = get_public_person(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
    )
    assert person is not None
    return PublicPersonMentionTimelineOut(
        person_id=person.id,
        label=person.label,
        items=items,
    )


@router.get("/{person_id}/mentions", response_model=PublicPersonMentionsOut)
def list_project_person_mentions(
    person_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    sort: Literal["article", "created_at"] = Query("created_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    nature: str | None = Query(None, description="Filter by mention nature"),
    author: str | None = Query(None, description="Filter by article byline (exact match)"),
    external_source: str | None = Query(
        None,
        description="Filter by publication/outlet name (exact match)",
    ),
    source: str | None = Query(
        None,
        description="Alias for external_source",
        deprecated=True,
    ),
    section: str | None = Query(
        None,
        description="Include mentions in articles with this subject metadata category",
    ),
    meta_type: str | None = Query(
        None,
        description="Include mentions in articles with this metadata type",
    ),
    meta_category: str | None = Query(
        None,
        description="With meta_type, include mentions in articles with this metadata category",
    ),
    exclude_meta_type: str | None = Query(
        None,
        description="Exclude mentions in articles with a metadata row of this type",
    ),
    exclude_meta_category: str | None = Query(
        None,
        description="With exclude_meta_type, exclude mentions in articles with this category",
    ),
    meta: list[str] = Query(default=[], description=META_PARAM_DESCRIPTION),
    pub_date_from: str | None = Query(None),
    pub_date_to: str | None = Query(None),
    quote: bool | None = Query(
        None,
        description="When true, return only mentions with quoted evidence",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PublicPersonMentionsOut:
    """Return paginated mention evidence for a canonical person in this project."""
    stylebook_id, project_id = resolve_public_people_scope(session, project)
    parsed_id = parse_person_id(person_id)
    outlet = external_source or source
    params = build_entity_mention_list_params(
        nature=nature,
        author=author,
        external_source=outlet,
        section=section,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        meta_clauses=parse_meta_clauses(meta),
        pub_date_from=parse_optional_date(pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(pub_date_to, param_name="pub_date_to"),
        quotes_only=quote is True,
        sort=sort,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )
    result = list_public_person_mentions(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=parsed_id,
        params=params,
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
