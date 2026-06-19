"""Shared helpers for public people routes."""

from __future__ import annotations

from uuid import UUID

from backfield_db import BackfieldProject
from backfield_entities.public.people import PublicPersonSearchParams, PublicPersonSort
from backfield_entities.public.stylebook_scope import resolve_public_stylebook_id
from fastapi import HTTPException, status
from sqlmodel import Session


def parse_person_id(person_id: str) -> str:
    value = person_id.strip()
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        ) from exc


def resolve_public_people_scope(
    session: Session,
    project: BackfieldProject,
) -> tuple[int, int]:
    try:
        stylebook_id = resolve_public_stylebook_id(session, project)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stylebook not found for project",
        ) from exc
    return stylebook_id, int(project.id)  # type: ignore[arg-type]


def build_person_search_params(
    *,
    q: str | None,
    person_type: str | None,
    public_figure: bool | None,
    title: str | None,
    affiliation: str | None,
    nature: str | None,
    min_mentions: int,
    sort: str | None,
    limit: int,
    offset: int,
) -> PublicPersonSearchParams:
    sort_value = PublicPersonSort.sort_key
    if sort:
        try:
            sort_value = PublicPersonSort(sort.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid sort. Use sort_key, recent, or label.",
            ) from exc
    return PublicPersonSearchParams(
        q=q,
        person_type=person_type,
        public_figure=public_figure,
        title=title,
        affiliation=affiliation,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort_value,
        limit=limit,
        offset=offset,
    )
