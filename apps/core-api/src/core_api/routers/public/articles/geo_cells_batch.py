"""POST /public/v1/projects/{project_slug}/articles/geo-cells/query."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_geo_cells_batch import (
    PublicArticleGeoCellsBatchItemOut,
    PublicArticleGeoCellsBatchParams,
    PublicArticleGeoCellsBatchResult,
    PublicArticleGeoCellsBatchValidationError,
    PublicArticleGeoCellTotalOut,
    search_public_articles_in_cells,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.articles.helpers import parse_optional_date
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicArticleGeoCellsBatchIn(BaseModel):
    cells: list[str] = Field(min_length=1, description="H3 cell IDs at the requested resolution")
    resolution: int = Field(ge=0, le=15, description="Display resolution shared by all cells")
    location_type: str | None = Field(
        default=None,
        description="Filter matching locations by substrate location_type",
    )
    nature: str | None = Field(
        default=None,
        description="Filter matching location mentions by editorial nature",
    )
    meta_type: str | None = Field(
        default=None,
        description="Include articles with a metadata row of this type",
    )
    meta_category: str | None = Field(
        default=None,
        description="With meta_type, include articles with this metadata category",
    )
    exclude_meta_type: str | None = Field(
        default=None,
        description="Exclude articles with a metadata row of this type",
    )
    exclude_meta_category: str | None = Field(
        default=None,
        description="With exclude_meta_type, exclude articles with this metadata category",
    )
    external_source: str | None = Field(
        default=None,
        description="Include articles from this external source (case-insensitive)",
    )
    pub_date_from: str | None = None
    pub_date_to: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    include_preview: bool = Field(
        default=False,
        description="Include a short text preview (max 280 characters) per article",
    )


class PublicArticleGeoCellsBatchOut(BaseModel):
    resolution: int
    items: list[PublicArticleGeoCellsBatchItemOut] = Field(default_factory=list)
    per_cell_totals: list[PublicArticleGeoCellTotalOut] = Field(default_factory=list)
    pagination: PaginationOut


@router.post("/geo-cells/query", response_model=PublicArticleGeoCellsBatchOut)
def query_project_articles_in_geo_cells(
    body: PublicArticleGeoCellsBatchIn,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleGeoCellsBatchOut:
    """Return articles and location mentions for many H3 cells in one request."""
    params = PublicArticleGeoCellsBatchParams(
        cells=tuple(body.cells),
        resolution=body.resolution,
        location_type=body.location_type,
        nature=body.nature,
        meta_type=body.meta_type,
        meta_category=body.meta_category,
        exclude_meta_type=body.exclude_meta_type,
        exclude_meta_category=body.exclude_meta_category,
        external_source=body.external_source,
        pub_date_from=parse_optional_date(body.pub_date_from, param_name="pub_date_from"),
        pub_date_to=parse_optional_date(body.pub_date_to, param_name="pub_date_to"),
        limit=body.limit,
        offset=body.offset,
        include_preview=body.include_preview,
    )
    try:
        result: PublicArticleGeoCellsBatchResult = search_public_articles_in_cells(
            session,
            project_id=int(project.id),  # type: ignore[arg-type]
            params=params,
        )
    except PublicArticleGeoCellsBatchValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return PublicArticleGeoCellsBatchOut(
        resolution=result.resolution,
        items=result.items,
        per_cell_totals=result.per_cell_totals,
        pagination=PaginationOut(limit=body.limit, offset=body.offset, total=result.total),
    )
