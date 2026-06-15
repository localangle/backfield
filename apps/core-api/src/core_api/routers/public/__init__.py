"""Consumer-facing public API (`/public/v1`).

Layout:
- ``deps.py``, ``schemas.py`` — shared dependencies and response envelopes
- ``projects/`` — project metadata
- ``articles/`` — article search, detail, and hub sub-routes (one module per route)
- ``entities/`` — canonical people, organizations, and locations
  (list, search, detail, mentions, articles, connections)
- ``mentions/`` — project-wide mention search, facets, and detail across entity types
"""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public import articles, entities, mentions, projects

router = APIRouter(tags=["public"])

router.include_router(projects.router)
router.include_router(articles.router)
router.include_router(entities.router)
router.include_router(mentions.router)
