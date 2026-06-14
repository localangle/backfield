"""Consumer-facing public API (`/public/v1`).

Layout:
- ``deps.py``, ``schemas.py`` — shared dependencies and response envelopes
- ``projects/`` — project metadata
- ``articles/`` — article search, detail, and hub sub-routes (one module per route)
- ``people/`` — canonical people list, search, detail, mentions, and connections
"""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public import articles, people, projects

router = APIRouter(tags=["public"])

router.include_router(projects.router)
router.include_router(articles.router)
router.include_router(people.router)
