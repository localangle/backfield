#!/usr/bin/env python3
"""Worker lifecycle smoke for the live Agate run path."""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import suppress

import httpx
from _helpers import (
    assert_object,
    ensure_health,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    wait_for_run_status,
    wait_for_terminal_run,
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()
SMOKE_POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
SMOKE_POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))


def _basic_graph_spec(text: str) -> dict[str, object]:
    return {
        "name": "smoke_worker_async",
        "nodes": [
            {
                "id": "text",
                "type": "TextInput",
                "params": {"text": text},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }


def main() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError("smoke-worker-async requires SMOKE_EMAIL and SMOKE_PASSWORD")

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

    graph_id: str | None = None
    graph_name = f"Smoke worker lifecycle {uuid.uuid4().hex[:8]}"
    text = f"worker lifecycle {uuid.uuid4().hex[:6]}"
    with httpx.Client(base_url=AGATE_API_BASE, timeout=15.0, headers=headers) as agate:
        try:
            graph = assert_object(
                agate.post(
                    "/graphs",
                    json={
                        "name": graph_name,
                        "project_id": ctx.project_id,
                        "spec": _basic_graph_spec(text),
                    },
                ),
                "create graph",
            )
            graph_id = str(graph["id"])

            run = assert_object(agate.post("/runs", json={"graph_id": graph_id}), "create run")
            if run.get("status") != "pending":
                raise RuntimeError(f"Expected initial pending status, got {run.get('status')!r}")

            first_progress = wait_for_run_status(
                agate,
                str(run["id"]),
                allowed_statuses={"running", "succeeded", "failed"},
                timeout_s=SMOKE_POLL_TIMEOUT_SECONDS,
                interval_s=SMOKE_POLL_INTERVAL_SECONDS,
            )
            terminal = wait_for_terminal_run(
                agate,
                str(run["id"]),
                timeout_s=SMOKE_POLL_TIMEOUT_SECONDS,
                interval_s=SMOKE_POLL_INTERVAL_SECONDS,
            )
            item_detail = assert_object(
                agate.get(f"/runs/{run['id']}/items/1"),
                "synthetic whole-run item detail",
            )
        finally:
            if graph_id and not keep_smoke_data():
                with suppress(Exception):
                    agate.delete(f"/graphs/{graph_id}").raise_for_status()

    if first_progress.get("status") not in {"running", "succeeded"}:
        raise RuntimeError(f"Run never advanced beyond pending: {first_progress!r}")
    if terminal.get("status") != "succeeded":
        raise RuntimeError(
            "Worker lifecycle smoke failed: "
            f"status={terminal.get('status')} error={terminal.get('error_message')}"
        )
    if item_detail.get("status") != "succeeded":
        raise RuntimeError(f"Unexpected whole-run item detail payload: {item_detail!r}")

    log("Smoke worker async passed.")
    log(f"Run: {terminal['id']}")
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
