#!/usr/bin/env python3
"""Stylebook import smoke using the GeoJSON import flow."""

from __future__ import annotations

import os
import sys
import uuid

import httpx
from _helpers import (
    assert_object,
    default_stylebook_for_org,
    delete_smoke_canonical,
    ensure_health,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    smoke_db_session,
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def main() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError(
            "smoke-stylebook-import-export requires SMOKE_EMAIL and SMOKE_PASSWORD"
        )

    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=SMOKE_WORKSPACE_SLUG,
        project_slug=SMOKE_PROJECT_SLUG,
    )
    headers = session_cookie_headers(ctx.session_token)
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=STYLEBOOK_API_BASE,
        core_base=CORE_API_BASE,
        agate_headers=headers,
        stylebook_headers=headers,
    )

    stylebook = default_stylebook_for_org(
        stylebook_base=STYLEBOOK_API_BASE,
        session_token=ctx.session_token,
        organization_id=ctx.organization_id,
    )
    stylebook_slug = str(stylebook["slug"])
    label = f"Smoke Import {uuid.uuid4().hex[:8]}"
    canonical_id: str | None = None
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                "properties": {
                    "name": label,
                    "type": "city",
                    "formatted_address": f"{label}, IL, USA",
                },
            }
        ],
    }

    try:
        with httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=20.0, headers=headers) as client:
            analyzed = assert_object(
                client.post(
                    f"/v1/stylebooks/{stylebook_slug}/import/geojson/analyze",
                    json={"geojson": geojson},
                ),
                "analyze geojson",
            )
            imported = assert_object(
                client.post(
                    f"/v1/stylebooks/{stylebook_slug}/import/geojson",
                    json={
                        "geojson": geojson,
                        "mappings": {
                            "label_property": "name",
                            "location_type_property": "type",
                            "formatted_address_property": "formatted_address",
                        },
                    },
                ),
                "import geojson",
            )

            created = imported.get("created")
            if not isinstance(created, list) or len(created) != 1:
                raise RuntimeError(f"Expected one created canonical row: {imported}")
            canonical_id = str(created[0]["canonical_id"])

            fetched = assert_object(
                client.get(
                    f"/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}",
                    params={"project": ctx.project_slug},
                ),
                "get imported canonical",
            )

        if int(analyzed.get("feature_count", -1)) != 1:
            raise RuntimeError(f"Unexpected analyze payload: {analyzed}")
        if (
            int(imported.get("created_count", -1)) != 1
            or int(imported.get("failed_count", -1)) != 0
        ):
            raise RuntimeError(f"Unexpected import payload: {imported}")
        if fetched.get("label") != label:
            raise RuntimeError(f"Imported canonical label mismatch: {fetched}")

        log("Smoke stylebook import passed.")
        log(f"Stylebook: {stylebook_slug!r}")
        log(f"Canonical: {canonical_id}")
        return 0
    finally:
        if canonical_id and not keep_smoke_data():
            with smoke_db_session() as session:
                delete_smoke_canonical(session, canonical_id=canonical_id)
                session.commit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
