#!/usr/bin/env python3
"""Session-shaped auth and permissions smoke against a live stack."""

from __future__ import annotations

import os
import sys

import httpx
from _helpers import (
    assert_list,
    assert_object,
    default_stylebook_for_org,
    ensure_health,
    http_error_detail,
    log,
    login_session_context,
    session_cookie_headers,
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
        raise RuntimeError("smoke-auth requires SMOKE_EMAIL and SMOKE_PASSWORD")

    log(
        f"Smoke auth: CORE_API_BASE={CORE_API_BASE} AGATE_API_BASE={AGATE_API_BASE} "
        f"STYLEBOOK_API_BASE={STYLEBOOK_API_BASE} workspace={SMOKE_WORKSPACE_SLUG!r} "
        f"project={SMOKE_PROJECT_SLUG!r}"
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

    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0, headers=headers) as agate:
        projects = assert_list(agate.get("/projects"), "Agate projects")
    project = next(
        (
            row
            for row in projects
            if isinstance(row, dict) and row.get("slug") == SMOKE_PROJECT_SLUG
        ),
        None,
    )
    if project is None:
        raise RuntimeError(f"Agate projects did not include slug {SMOKE_PROJECT_SLUG!r}")
    if int(project["id"]) != ctx.project_id:
        raise RuntimeError(
            "Agate project scope did not match Core workspace scope "
            f"(Core id={ctx.project_id}, Agate id={project['id']})"
        )

    stylebook = default_stylebook_for_org(
        stylebook_base=STYLEBOOK_API_BASE,
        session_token=ctx.session_token,
        organization_id=ctx.organization_id,
    )
    stylebook_slug = str(stylebook["slug"])

    with httpx.Client(
        base_url=STYLEBOOK_API_BASE,
        timeout=10.0,
        headers=headers,
    ) as stylebook_client:
        perms = assert_object(
            stylebook_client.get(f"/v1/stylebooks/{stylebook_slug}/permissions"),
            "Stylebook permissions",
        )
    if perms.get("can_edit") is not True:
        raise RuntimeError(
            f"Expected can_edit=true for stylebook {stylebook_slug!r}, got {perms}"
        )

    log("Smoke auth passed.")
    log(f"User: {ctx.user.get('email')!r}")
    log(f"Project: {SMOKE_PROJECT_SLUG} ({ctx.project_id})")
    log(f"Stylebook: {stylebook_slug!r}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
