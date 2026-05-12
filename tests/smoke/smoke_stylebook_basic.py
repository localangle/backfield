#!/usr/bin/env python3
"""Basic Stylebook write-path smoke with canonical creation."""

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
        raise RuntimeError("smoke-stylebook-basic requires SMOKE_EMAIL and SMOKE_PASSWORD")

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
    label = f"Smoke basic canonical {uuid.uuid4().hex[:8]}"
    canonical_id: str | None = None

    try:
        with httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=15.0, headers=headers) as client:
            created = assert_object(
                client.post(
                    f"/v1/stylebooks/{stylebook_slug}/canonical-locations",
                    params={"project": ctx.project_slug},
                    json={"label": label, "location_type": "city"},
                ),
                "create canonical",
            )
            canonical_id = str(created["id"])
            fetched = assert_object(
                client.get(
                    f"/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}",
                    params={"project": ctx.project_slug},
                ),
                "get canonical",
            )

        if created.get("label") != label or fetched.get("label") != label:
            raise RuntimeError(
                f"Canonical label round-trip mismatch: created={created.get('label')!r} "
                f"fetched={fetched.get('label')!r}"
            )
        if int(created.get("linked_substrate_count", -1)) != 0:
            raise RuntimeError(f"New canonical should not have linked substrates yet: {created!r}")
        if int(fetched.get("linked_substrate_count", -1)) != 0:
            raise RuntimeError(
                f"Fetched canonical should not have linked substrates yet: {fetched!r}"
            )

        log("Smoke stylebook basic passed.")
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
