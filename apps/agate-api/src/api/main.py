"""Agate API — FastAPI control plane."""

from __future__ import annotations

import os

from api.routers import graphs, health, nodes, projects, runs, templates
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

UI_ORIGIN = os.getenv("UI_ORIGIN", "http://localhost:5173")
if UI_ORIGIN.startswith("http://localhost") or UI_ORIGIN.startswith("http://127.0.0.1"):
    ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5175", "http://127.0.0.1:5175"]
else:
    ALLOWED_ORIGINS = [UI_ORIGIN]

app = FastAPI(
    title="Agate API",
    description="Backfield Agate control plane",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(graphs.router)
app.include_router(templates.router)
app.include_router(runs.router)
app.include_router(nodes.router)
