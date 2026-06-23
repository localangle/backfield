"""Public article read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.articles import (
    custom_records,
    detail,
    facets,
    geo_cell_detail,
    geo_cells,
    geo_cells_batch,
    geo_search,
    images,
    locations,
    mentions,
    metadata,
    organizations,
    people,
    search,
    semantic_search,
)

router = APIRouter(prefix="/projects/{project_slug}/articles", tags=["public-articles"])

# Register static paths before parameterized routes.
router.include_router(search.router)
router.include_router(facets.router)
router.include_router(metadata.router)
router.include_router(semantic_search.router)
router.include_router(geo_search.router)
router.include_router(geo_cells.router)
router.include_router(geo_cells_batch.router)
router.include_router(geo_cell_detail.router)
router.include_router(detail.router)
router.include_router(mentions.router)
router.include_router(locations.router)
router.include_router(people.router)
router.include_router(organizations.router)
router.include_router(custom_records.router)
router.include_router(images.router)

__all__ = ["router"]
