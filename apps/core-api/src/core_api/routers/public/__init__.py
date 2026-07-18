"""Consumer-facing public API (`/public/v1`).

Layout:
- ``deps.py``, ``schemas.py`` — shared dependencies and response envelopes
- ``projects/`` — project metadata
- ``articles/`` — article search, detail, and hub sub-routes (one module per route)
- ``entities/`` — canonical people, organizations, and locations
  (list, search, detail, mentions, articles, connections)
- ``mentions/`` — project-wide mention search, facets, and detail across entity types
- ``runs/`` — run trigger and status polling (``runs:trigger`` scope)
"""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public import articles, entities, mentions, projects, runs
from core_api.routers.public.errors import PUBLIC_ERROR_RESPONSES

router = APIRouter(tags=["public"], responses=PUBLIC_ERROR_RESPONSES)

router.include_router(projects.router)
router.include_router(articles.router)
router.include_router(entities.router)
router.include_router(mentions.router)
router.include_router(runs.router)
