"""Article metadata discovery routes."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_metadata import (
    PublicArticleMetadataOut,
    PublicArticleMetaTypesOut,
    PublicArticleMetaValuesOut,
    get_public_article_metadata,
    list_public_article_meta_types,
    list_public_article_meta_values,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project

router = APIRouter()


@router.get("/metadata/types", response_model=PublicArticleMetaTypesOut)
def list_project_article_metadata_types(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleMetaTypesOut:
    """Return distinct metadata types attached to articles in this project."""
    return list_public_article_meta_types(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
    )


@router.get(
    "/metadata/types/{meta_type}/values",
    response_model=PublicArticleMetaValuesOut,
)
def list_project_article_metadata_values(
    meta_type: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleMetaValuesOut:
    """Return distinct category values for one metadata type in this project."""
    normalized_type = meta_type.strip()
    if not normalized_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="meta_type must not be empty.",
        )
    return list_public_article_meta_values(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        meta_type=normalized_type,
    )


@router.get("/{article_id}/metadata", response_model=PublicArticleMetadataOut)
def get_project_article_metadata(
    article_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleMetadataOut:
    """Return metadata rows and distinct types for one article."""
    result = get_public_article_metadata(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return result
