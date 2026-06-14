"""Public article read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.articles import detail, images, locations, mentions, search

router = APIRouter(prefix="/projects/{project_slug}/articles", tags=["public-articles"])

# Register static paths before parameterized routes.
router.include_router(search.router)
router.include_router(detail.router)
router.include_router(mentions.router)
router.include_router(locations.router)
router.include_router(images.router)

__all__ = ["router"]
