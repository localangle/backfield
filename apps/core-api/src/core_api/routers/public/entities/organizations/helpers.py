"""Shared helpers for public organization routes."""

from __future__ import annotations

from uuid import UUID

from backfield_db import BackfieldProject
from backfield_entities.catalog.resolve import STYLEBOOK_SLUG_NOT_IN_ORG
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
    *,
    stylebook_slug: str | None = None,
) -> tuple[int, int]:
    try:
        stylebook_id = resolve_public_stylebook_id(
            session, project, stylebook_slug=stylebook_slug
        )
    except LookupError as exc:
        detail = (
            "Stylebook not found"
            if str(exc) == STYLEBOOK_SLUG_NOT_IN_ORG
            else "Stylebook not found for project"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
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
