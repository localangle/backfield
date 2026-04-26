"""Stylebook API — companion service for Agate (geocode, canonical entities)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stylebook_api.routers import (
    connections,
    geocode,
    health,
    location_candidates,
    location_meta,
    locations,
    stylebooks,
    ui_stubs,
)

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

app.include_router(health.router)
app.include_router(stylebooks.router)
app.include_router(geocode.router)
app.include_router(locations.router)
app.include_router(location_candidates.router)
app.include_router(location_meta.router)
app.include_router(connections.connections_router, prefix="/v1/connections")
app.include_router(connections.locations_connections_router)
app.include_router(ui_stubs.router)
