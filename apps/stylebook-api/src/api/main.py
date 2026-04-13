"""Stylebook API — companion service for Agate (geocode, future entities)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Stylebook API", version="0.1.0")

UI_ORIGIN = os.getenv("UI_ORIGIN", "http://localhost:5175")
if UI_ORIGIN.startswith("http://localhost"):
    ALLOWED = [
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:8000",
        "http://localhost:8001",
    ]
else:
    ALLOWED = [UI_ORIGIN]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Minimal demo gazetteer for starter pipelines
_GAZETTEER: dict[str, dict[str, Any]] = {
    "chicago, il": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
    "austin, tx": {"lat": 30.2672, "lon": -97.7431, "label": "Austin, TX"},
    "minneapolis, mn": {"lat": 44.9778, "lon": -93.2650, "label": "Minneapolis, MN"},
}


def verify_service(authorization: str | None = Header(None)) -> None:
    token = os.environ.get("SERVICE_API_TOKEN", "")
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing service auth")
    got = authorization.removeprefix("Bearer ").strip()
    if got != token:
        raise HTTPException(401, "Invalid service token")


class GeocodeBody(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"ok": True, "service": "stylebook-api"}


@app.post("/v1/geocode/resolve")
def geocode_resolve(
    body: GeocodeBody,
    _auth: None = Depends(verify_service),
):
    """Resolve a free-text location string to coordinates (starter stub)."""
    key = body.query.strip().lower()
    hit = _GAZETTEER.get(key)
    if hit:
        return hit
    # Prefix / partial match
    for k, v in _GAZETTEER.items():
        if key in k or k in key:
            return v
    return {"lat": None, "lon": None, "label": body.query, "note": "unresolved_stub"}
