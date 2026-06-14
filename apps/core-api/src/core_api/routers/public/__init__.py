"""Consumer-facing public API (`/public/v1`).

Layout:
- ``deps.py``, ``schemas.py`` — shared dependencies and response envelopes
- ``projects/`` — project metadata
- ``articles/`` — article search, detail, and hub sub-routes (one module per route)
"""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public import articles, projects

router = APIRouter(tags=["public"])

router.include_router(projects.router)
router.include_router(articles.router)
