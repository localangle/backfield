"""Consumer-facing public API (`/public/v1`)."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public import projects

router = APIRouter(tags=["public"])

router.include_router(projects.router)
