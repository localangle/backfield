"""Public project-wide mention read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.mentions import detail, facets, search

router = APIRouter(prefix="/projects/{project_slug}/mentions", tags=["public-mentions"])

router.include_router(search.router)
router.include_router(facets.router)
router.include_router(detail.router)

__all__ = ["router"]
