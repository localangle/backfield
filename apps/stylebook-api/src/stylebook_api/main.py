"""Stylebook API — companion service for Agate (canonical entities and catalogs)."""

from __future__ import annotations

import os

from backfield_auth.path_prefix import install_path_prefix
from backfield_auth.request_logging_middleware import RequestLoggingMiddleware
from backfield_auth.structured_logging import configure_structured_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stylebook_api.entities.location import candidates, locations, meta
from stylebook_api.entities.organization import candidates as organization_candidates
from stylebook_api.entities.organization import meta as organization_meta
from stylebook_api.entities.organization import organizations
from stylebook_api.entities.person import candidates as person_candidates
from stylebook_api.entities.person import meta as person_meta
from stylebook_api.entities.person import people
from stylebook_api.routers import (
    connections,
    health,
    imports,
    semantic_mention_search,
    stats,
    stylebook_activity,
    stylebook_bundle_jobs,
    stylebook_candidate_ai_review,
    stylebook_canonicals,
    stylebook_cleanup,
    stylebook_cleanup_ai_review,
    stylebook_organization_canonicals,
    stylebook_permissions,
    stylebook_person_canonicals,
    stylebooks,
    taxonomy,
)

configure_structured_logging("stylebook-api")

UI_ORIGIN = os.getenv("UI_ORIGIN", "http://localhost:5175")
PLAYGROUND_ORIGIN = os.getenv(
    "PLAYGROUND_ORIGIN",
    "",
)
# Optional regex override for non-production experiments only. Production should leave this
# empty and set an exact per-deployment PLAYGROUND_ORIGIN instead.
PLAYGROUND_ORIGIN_REGEX = os.getenv("PLAYGROUND_ORIGIN_REGEX", "").strip()
if UI_ORIGIN.startswith("http://localhost"):
    ALLOWED = [
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        PLAYGROUND_ORIGIN,
    ]
else:
    ALLOWED = [UI_ORIGIN, PLAYGROUND_ORIGIN]
ALLOWED = [origin for origin in ALLOWED if origin and origin.strip()]

app = FastAPI(title="Stylebook API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_origin_regex=PLAYGROUND_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware, service_name="stylebook-api")
# Outermost: strip CloudFront path prefix (e.g. /api/stylebook) before routing.
install_path_prefix(app)

app.include_router(health.router)
app.include_router(taxonomy.router)
app.include_router(stylebooks.router)
app.include_router(stylebook_bundle_jobs.router)
app.include_router(stylebook_activity.router)
app.include_router(locations.router)
app.include_router(imports.router)
app.include_router(imports.stylebook_router)
app.include_router(candidates.router)
app.include_router(meta.router)
app.include_router(stylebook_canonicals.router)
app.include_router(stylebook_cleanup.router)
app.include_router(stylebook_cleanup_ai_review.router)
app.include_router(stylebook_candidate_ai_review.router)
app.include_router(stylebook_person_canonicals.router)
app.include_router(stylebook_organization_canonicals.router)
app.include_router(stylebook_permissions.router)
app.include_router(connections.connections_router, prefix="/v1/connections")
app.include_router(connections.locations_connections_router)
app.include_router(person_candidates.router)
app.include_router(people.router)
app.include_router(person_meta.router)
app.include_router(organization_candidates.router)
app.include_router(organizations.router)
app.include_router(organization_meta.router)
app.include_router(semantic_mention_search.router)
app.include_router(stats.router)
