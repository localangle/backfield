"""Shared helpers for public organization routes."""

from __future__ import annotations

from uuid import UUID

from backfield_db import BackfieldProject
from backfield_entities.public.organizations import (
    PublicOrganizationSearchParams,
    PublicOrganizationSort,
)
from backfield_entities.public.stylebook_scope import resolve_public_stylebook_id
from fastapi import HTTPException, status
from sqlmodel import Session


def parse_organization_id(organization_id: str) -> str:
    value = organization_id.strip()
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from exc


def resolve_public_organizations_scope(
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


def build_organization_search_params(
    *,
    q: str | None,
    organization_type: str | None,
    nature: str | None,
    min_mentions: int,
    sort: str | None,
    limit: int,
    offset: int,
) -> PublicOrganizationSearchParams:
    sort_value = PublicOrganizationSort.label
    if sort:
        try:
            sort_value = PublicOrganizationSort(sort.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid sort. Use label or recent.",
            ) from exc
    return PublicOrganizationSearchParams(
        q=q,
        organization_type=organization_type,
        nature=nature,
        min_mentions=min_mentions,
        sort=sort_value,
        limit=limit,
        offset=offset,
    )
