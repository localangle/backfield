"""GeocodeAgent — calls Stylebook API geocode helper."""

from __future__ import annotations

import os
from typing import Any

import httpx


def run_geocode_agent(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    locations = inputs.get("locations") or []
    if not isinstance(locations, list):
        locations = []

    base = os.environ.get("STYLEBOOK_API_URL", "http://localhost:8003").rstrip("/")
    token = os.environ.get("SERVICE_API_TOKEN", "")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        for loc in locations:
            if isinstance(loc, dict):
                q = loc.get("location") or loc.get("query") or str(loc)
            else:
                q = str(loc)
            r = client.post(
                f"{base}/v1/geocode/resolve",
                json={"query": q},
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            merged = {**loc} if isinstance(loc, dict) else {"location": q}
            merged["geocode"] = data
            out.append(merged)

    return {"locations": out}
