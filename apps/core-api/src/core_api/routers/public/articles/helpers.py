"""Shared helpers for public article routes."""

from __future__ import annotations

from datetime import date

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import PublicEntityMentionType
from backfield_entities.public.article_scope import get_public_article_row
from fastapi import HTTPException, status
from sqlmodel import Session


def parse_optional_date(value: str | None, *, param_name: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {param_name}. Use YYYY-MM-DD.",
        ) from exc


def parse_include(include: str | None) -> set[str]:
    if not include or not include.strip():
        return set()
    return {part.strip().lower() for part in include.split(",") if part.strip()}


def require_article(
    session: Session,
    project: BackfieldProject,
    article_id: int,
):
    article = get_public_article_row(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def parse_entity_type(value: str | None) -> PublicEntityMentionType | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in ("location", "person", "organization"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entity_type. Use location, person, or organization.",
        )
    return normalized  # type: ignore[return-value]


def parse_bbox(value: str | None) -> tuple[float, float, float, float]:
    if value is None or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox is required in format min_lng,min_lat,max_lng,max_lat.",
        )
    parts = value.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox must be in format min_lng,min_lat,max_lng,max_lat.",
        )
    try:
        min_lng, min_lat, max_lng, max_lat = (float(part.strip()) for part in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox values must be valid numbers.",
        ) from exc
    return min_lng, min_lat, max_lng, max_lat
