"""Public canonical people read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.entities.people import (
    articles,
    connections,
    detail,
    list_search,
    mentions,
    types,
)

router = APIRouter(prefix="/projects/{project_slug}/people", tags=["public-people"])

router.include_router(types.router)
router.include_router(list_search.router)
router.include_router(mentions.router)
router.include_router(articles.router)
router.include_router(connections.router)
router.include_router(detail.router)

__all__ = ["router"]
