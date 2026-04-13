#!/usr/bin/env python3
"""Golden-path smoke test for a live Backfield stack."""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "45"))
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


def _fallback_graph_spec() -> dict:
    return {
        "name": "smoke_flow",
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "We visited Chicago, IL and Austin, TX."},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n2",
                "type": "PlaceExtract",
                "params": {},
                "position": {"x": 220, "y": 0},
            },
            {
                "id": "n3",
                "type": "GeocodeAgent",
                "params": {},
                "position": {"x": 440, "y": 0},
            },
            {
                "id": "n4",
                "type": "Output",
                "params": {},
                "position": {"x": 660, "y": 0},
            },
        ],
        "edges": [
            {"source": "n1", "target": "n2", "sourceHandle": "text", "targetHandle": "text"},
            {
                "source": "n2",
                "target": "n3",
                "sourceHandle": "locations",
                "targetHandle": "locations",
            },
            {
                "source": "n3",
                "target": "n4",
                "sourceHandle": "locations",
                "targetHandle": "data",
            },
        ],
    }


def main() -> int:
    slug = f"smoke-{uuid.uuid4().hex[:8]}"
    created_project_id: int | None = None
    created_graph_id: str | None = None

    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0) as agate_client:
        stylebook_client = httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=10.0)
        try:
            agate_health = _assert_ok(agate_client.get("/health"), "Agate health")
            stylebook_health = _assert_ok(stylebook_client.get("/health"), "Stylebook health")
            if agate_health.get("ok") is not True:
                raise RuntimeError(f"Agate health failed: {agate_health}")
            if stylebook_health.get("ok") is not True:
                raise RuntimeError(f"Stylebook health failed: {stylebook_health}")

            project = _assert_ok(
                agate_client.post("/projects", json={"name": "Smoke Project", "slug": slug}),
                "create project",
            )
            created_project_id = int(project["id"])

            templates_response = agate_client.get("/templates")
            templates_response.raise_for_status()
            templates = templates_response.json()
            if templates:
                template_id = templates[0]["id"]
                graph = _assert_ok(
                    agate_client.post(
                        f"/templates/{template_id}/instantiate",
                        json={"project_id": created_project_id, "name": "Smoke Flow"},
                    ),
                    "instantiate template",
                )
            else:
                graph = _assert_ok(
                    agate_client.post(
                        "/graphs",
                        json={
                            "name": "Smoke Flow",
                            "project_id": created_project_id,
                            "spec": _fallback_graph_spec(),
                        },
                    ),
                    "create fallback graph",
                )
            created_graph_id = str(graph["id"])

            run = _assert_ok(
                agate_client.post("/runs", json={"graph_id": created_graph_id}),
                "create run",
            )
            terminal_run = _wait_for_terminal_run(agate_client, str(run["id"]))
            if terminal_run.get("status") != "succeeded":
                raise RuntimeError(
                    "Smoke run failed: "
                    f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
                )

            print("Smoke passed.")
            print(f"Project: {created_project_id}")
            print(f"Graph: {created_graph_id}")
            print(f"Run: {terminal_run['id']}")
            return 0
        finally:
            if created_graph_id is not None:
                agate_client.delete(f"/graphs/{created_graph_id}")
            if created_project_id is not None:
                agate_client.delete(f"/projects/{created_project_id}")
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
