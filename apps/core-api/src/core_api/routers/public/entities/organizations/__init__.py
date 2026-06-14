"""Public canonical organization read routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.organizations import (
    connections,
    detail,
    list_search,
    mentions,
    types,
)

router = APIRouter(prefix="/projects/{project_slug}/organizations", tags=["public-organizations"])

router.include_router(types.router)
router.include_router(list_search.router)
router.include_router(mentions.router)
router.include_router(connections.router)
router.include_router(detail.router)

__all__ = ["router"]
