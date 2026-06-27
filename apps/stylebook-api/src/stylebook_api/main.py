"""Stylebook API — companion service for Agate (geocode, canonical entities)."""

from __future__ import annotations

import os

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
    geocode,
    health,
    imports,
    semantic_mention_search,
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
    ui_stubs,
)

configure_structured_logging("stylebook-api")

UI_ORIGIN = os.getenv("UI_ORIGIN", "http://localhost:5175")
if UI_ORIGIN.startswith("http://localhost"):
    ALLOWED = [
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
else:
    ALLOWED = [UI_ORIGIN]

app = FastAPI(title="Stylebook API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware, service_name="stylebook-api")

app.include_router(health.router)
app.include_router(taxonomy.router)
app.include_router(stylebooks.router)
app.include_router(stylebook_bundle_jobs.router)
app.include_router(geocode.router)
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
app.include_router(ui_stubs.router)
