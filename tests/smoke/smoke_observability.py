"""Observability smoke: local EMF checks, plus optional live success/failure runs.

Without ``SMOKE_EMAIL`` / ``SMOKE_PASSWORD``, only verifies local EMF emission.
With credentials and a live stack, also creates one success and one failed run.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import redirect_stderr
from datetime import UTC, datetime
from io import StringIO

import httpx
from backfield_observability.identity import read_runtime_identity
from backfield_observability.lifecycle import emit_item_terminal, emit_run_terminal

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")


def _assert_local_emf(captured: StringIO) -> None:
    lines = [
        json.loads(line)
        for line in captured.getvalue().splitlines()
        if line.strip()
    ]
    names = {
        line.get("metric_name")
        for line in lines
        if line.get("event") == "cloudwatch_emf"
    }
    assert "runs_completed_total" in names, names
    assert "items_failed_total" in names, names
    assert any(line.get("run_id") == "smoke-local-run" for line in lines)


def _emit_local_metrics() -> StringIO:
    if not os.environ.get("BACKFIELD_CLIENT"):
        os.environ["BACKFIELD_CLIENT"] = "smoke-local"
    captured = StringIO()
    with redirect_stderr(captured):
        identity = read_runtime_identity("worker")
        emit_run_terminal(
            previous_status="running",
            new_status="succeeded",
            identity=identity,
            correlation={"run_id": "smoke-local-run"},
        )
        emit_item_terminal(
            previous_status="running",
            new_status="failed",
            identity=identity,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            correlation={"run_id": "smoke-local-run", "item_id": "1"},
        )
    return captured


def _live_runs() -> None:
    # Local smoke helper imports (tests/smoke on sys.path when run via make).
    from _helpers import (  # type: ignore[import-not-found]
        assert_object,
        ensure_health,
        login_session_context,
        session_cookie_headers,
        wait_for_terminal_run,
    )

    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip(),
        project_slug=os.environ.get("SMOKE_PROJECT_SLUG", "general").strip(),
    )
    headers = session_cookie_headers(ctx.session_token)
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003"),
        core_base=CORE_API_BASE,
        agate_headers=headers,
        stylebook_headers=headers,
    )
    success_spec = {
        "name": "obs-success",
        "nodes": [
            {
                "id": "t",
                "type": "TextInput",
                "params": {"text": "Observability smoke."},
                "position": {"x": 0, "y": 0},
            },
            {"id": "out", "type": "Output", "params": {}, "position": {"x": 220, "y": 0}},
        ],
        "edges": [
            {
                "source": "t",
                "target": "out",
                "sourceHandle": "text",
                "targetHandle": "data",
            }
        ],
    }
    fail_spec = {
        "name": "obs-fail",
        "nodes": [
            {
                "id": "t",
                "type": "TextInput",
                "params": {"text": "Observability fail smoke."},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "bad",
                "type": "DefinitelyNotARealNode",
                "params": {},
                "position": {"x": 120, "y": 0},
            },
            {"id": "out", "type": "Output", "params": {}, "position": {"x": 220, "y": 0}},
        ],
        "edges": [
            {
                "source": "t",
                "target": "bad",
                "sourceHandle": "text",
                "targetHandle": "data",
            },
            {
                "source": "bad",
                "target": "out",
                "sourceHandle": "data",
                "targetHandle": "data",
            },
        ],
    }
    with httpx.Client(base_url=AGATE_API_BASE, timeout=30.0, headers=headers) as client:
        graphs: list[str] = []
        try:
            for name, spec, expect in (
                (f"obs-ok-{uuid.uuid4().hex[:6]}", success_spec, "succeeded"),
                (f"obs-fail-{uuid.uuid4().hex[:6]}", fail_spec, "failed"),
            ):
                graph = assert_object(
                    client.post(
                        "/graphs",
                        json={
                            "name": name,
                            "project_id": ctx.project_id,
                            "spec": spec,
                        },
                    ),
                    "create graph",
                )
                graphs.append(str(graph["id"]))
                run = assert_object(
                    client.post("/runs", json={"graph_id": graph["id"]}),
                    "create run",
                )
                terminal = wait_for_terminal_run(
                    client,
                    str(run["id"]),
                    timeout_seconds=180.0,
                    interval_seconds=1.5,
                )
                assert terminal["status"] == expect, terminal
                print(f"{expect}_run={terminal['id']}")
        finally:
            for graph_id in graphs:
                client.delete(f"/graphs/{graph_id}")


def main() -> int:
    captured = _emit_local_metrics()
    _assert_local_emf(captured)
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        print("observability smoke (local EMF only) ok")
        return 0
    _live_runs()
    print("observability smoke (local EMF + live runs) ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
