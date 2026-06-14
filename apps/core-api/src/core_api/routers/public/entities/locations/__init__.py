"""Public canonical location read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.locations import (
    connections,
    detail,
    geo_search,
    list_search,
    mentions,
    types,
)

router = APIRouter(prefix="/projects/{project_slug}/locations", tags=["public-locations"])

router.include_router(types.router)
router.include_router(geo_search.router)
router.include_router(list_search.router)
router.include_router(mentions.router)
router.include_router(connections.router)
router.include_router(detail.router)

__all__ = ["router"]
