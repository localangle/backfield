#!/usr/bin/env python3
"""Golden-path smoke test for a live Backfield stack."""

from __future__ import annotations

import os
import sys
import time

import httpx
from backfield_core import STARTER_FLOW_GRAPH_DISPLAY_NAME, starter_geocode_flow_graph_spec

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
# LLM PlaceExtract + GeocodeAgent can exceed 45s on cold starts.
POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))


def _assert_ok(response: httpx.Response, context: str) -> dict:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} returned a non-object payload: {payload!r}")
    return payload


def _wait_for_terminal_run(client: httpx.Client, run_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        payload = _assert_ok(client.get(f"/runs/{run_id}"), f"run {run_id}")
        status = payload.get("status")
        if status in {"succeeded", "failed"}:
            return payload
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Timed out waiting for run {run_id} to finish")


def main() -> int:
    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0) as agate_client:
        stylebook_client = httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=10.0)
        try:
            agate_health = _assert_ok(agate_client.get("/health"), "Agate health")
            stylebook_health = _assert_ok(stylebook_client.get("/health"), "Stylebook health")
            if agate_health.get("ok") is not True:
                raise RuntimeError(f"Agate health failed: {agate_health}")
            if stylebook_health.get("ok") is not True:
                raise RuntimeError(f"Stylebook health failed: {stylebook_health}")

            projects = agate_client.get("/projects")
            projects.raise_for_status()
            plist = projects.json()
            if not isinstance(plist, list):
                raise RuntimeError(f"list projects: expected list, got {type(plist)}")
            general = next((p for p in plist if p.get("slug") == "general"), None)
            if general is None:
                raise RuntimeError(
                    "Smoke needs the seeded 'General' project (slug general). "
                    "Run migrations (agate-api entrypoint or make migrate)."
                )
            project_id = int(general["id"])

            graphs = agate_client.get("/graphs")
            graphs.raise_for_status()
            glist = graphs.json()
            if not isinstance(glist, list):
                raise RuntimeError(f"list graphs: expected list, got {type(glist)}")
            starter = next(
                (
                    g
                    for g in glist
                    if g.get("project_id") == project_id
                    and g.get("name") == STARTER_FLOW_GRAPH_DISPLAY_NAME
                ),
                None,
            )
            if starter is None:
                spec = starter_geocode_flow_graph_spec()
                raise RuntimeError(
                    f"Smoke needs graph named {STARTER_FLOW_GRAPH_DISPLAY_NAME!r} on General. "
                    "Start the stack with BACKFIELD_LOCAL_BOOTSTRAP=1 (see docker-compose) "
                    f"or create it with spec name {spec.name!r}."
                )
            graph_id = str(starter["id"])

            run = _assert_ok(
                agate_client.post("/runs", json={"graph_id": graph_id}),
                "create run",
            )
            terminal_run = _wait_for_terminal_run(agate_client, str(run["id"]))
            if terminal_run.get("status") != "succeeded":
                raise RuntimeError(
                    "Smoke run failed: "
                    f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
                )

            print("Smoke passed.")
            print(f"Project: {project_id} (general)")
            print(f"Graph: {graph_id} ({STARTER_FLOW_GRAPH_DISPLAY_NAME})")
            print(f"Run: {terminal_run['id']}")
            return 0
        finally:
            stylebook_client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
