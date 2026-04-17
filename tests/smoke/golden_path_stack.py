#!/usr/bin/env python3
"""Golden-path smoke for a live Backfield stack.

Two modes (pick automatically):

1. **Session (UI-shaped)** — when ``SMOKE_EMAIL`` and ``SMOKE_PASSWORD`` are set: log in to
   Core API, load workspaces like the home page, resolve the General project from that view,
   then call Agate with the same ``session`` cookie to list graphs and enqueue a run.

2. **Service Bearer** — otherwise: same as the historical smoke (``Authorization: Bearer``),
   for automation that does not provision Core credentials (e.g. CI without Core login).

Values are read from the process environment. The repo-root ``.env`` (if present) is loaded
first with **python-dotenv**; variables already set in the shell take precedence.

Environment (common):

- ``AGATE_API_BASE`` (default ``http://localhost:8000``)
- ``STYLEBOOK_API_BASE`` (default ``http://localhost:8003``)
- ``CORE_API_BASE`` (default ``http://localhost:8004``) — session mode only
- ``SMOKE_POLL_TIMEOUT_SECONDS`` (default ``180``),
  ``SMOKE_POLL_INTERVAL_SECONDS`` (default ``1.5``)

Session mode:

- ``SMOKE_EMAIL``, ``SMOKE_PASSWORD`` — required
- ``SMOKE_WORKSPACE_SLUG`` (default ``default``) — workspace to open
- ``SMOKE_PROJECT_SLUG`` (default ``general``)
- Optional: ``SMOKE_BOOTSTRAP=1`` to POST ``/v1/bootstrap/first-user`` first (empty DB only)

Service Bearer mode:

- ``SMOKE_AGATE_BEARER`` or ``SERVICE_API_TOKEN`` (default ``backfield-dev``)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from backfield_core import (
    STARTER_FLOW_GRAPH_DISPLAY_NAME,
    GraphSpec,
    starter_geocode_flow_graph_spec,
)


def _load_repo_dotenv() -> None:
    """Load repo-root ``.env`` so ``make smoke`` picks up ``SMOKE_*`` without manual ``export``."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path, override=False)


_load_repo_dotenv()

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_AGATE_BEARER = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
    "SERVICE_API_TOKEN", "backfield-dev"
)
POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))

SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        r = exc.response
        body = (r.text or "")[:4000]
        return f"{r.status_code} {r.request.method} {r.request.url!s}\n{body}"
    return str(exc)


def _assert_ok(response: httpx.Response, context: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} returned a non-object payload: {payload!r}")
    return payload


def _wait_for_terminal_run(client: httpx.Client, run_id: str) -> dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        payload = _assert_ok(client.get(f"/runs/{run_id}"), f"run {run_id}")
        status = payload.get("status")
        if status in {"succeeded", "failed"}:
            return payload
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Timed out waiting for run {run_id} to finish")


def _health_checks(agate_client: httpx.Client) -> None:
    stylebook_client = httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=10.0)
    try:
        agate_health = _assert_ok(agate_client.get("/health"), "Agate health")
        stylebook_health = _assert_ok(stylebook_client.get("/health"), "Stylebook health")
        if agate_health.get("ok") is not True:
            raise RuntimeError(f"Agate health failed: {agate_health}")
        if stylebook_health.get("ok") is not True:
            raise RuntimeError(f"Stylebook health failed: {stylebook_health}")
    finally:
        stylebook_client.close()


def _edge_signature(e: Any) -> tuple[str | None, str | None, str | None, str | None]:
    """Normalize edge tuple for comparison (handles optional / null)."""
    if hasattr(e, "source"):
        return (e.source, e.target, e.sourceHandle, e.targetHandle)
    if isinstance(e, dict):
        return (
            e.get("source"),
            e.get("target"),
            e.get("sourceHandle"),
            e.get("targetHandle"),
        )
    raise RuntimeError(f"Invalid edge shape: {type(e).__name__}")


def _assert_starter_graph_matches_bootstrap(starter: dict[str, Any]) -> None:
    """Starter flow topology must match bootstrap.

    Expected chain: TextInput → PlaceExtract → GeocodeAgent → DBOutput.
    """
    spec_raw = starter.get("spec")
    if not isinstance(spec_raw, dict):
        raise RuntimeError("Starter flow graph payload missing object 'spec'")
    current = GraphSpec.model_validate(spec_raw)
    canonical = starter_geocode_flow_graph_spec()

    if current.name != canonical.name:
        raise RuntimeError(
            f"Starter flow spec.name expected {canonical.name!r}, got {current.name!r}. "
            "Restart agate-api with BACKFIELD_LOCAL_BOOTSTRAP=1 so local bootstrap rewrites it."
        )

    want_nodes = {(n.id, n.type) for n in canonical.nodes}
    have_nodes = {(n.id, n.type) for n in current.nodes}
    if have_nodes != want_nodes:
        raise RuntimeError(
            "Starter flow nodes do not match canonical bootstrap "
            f"(expected {sorted(want_nodes)!r}, have {sorted(have_nodes)!r}). "
            "Restart agate-api with BACKFIELD_LOCAL_BOOTSTRAP=1."
        )

    want_edges = {_edge_signature(e) for e in canonical.edges}
    have_edges = {_edge_signature(e) for e in current.edges}
    if have_edges != want_edges:
        raise RuntimeError(
            "Starter flow edges do not match canonical bootstrap. "
            "Restart agate-api with BACKFIELD_LOCAL_BOOTSTRAP=1."
        )

    if any(n.type == "Output" for n in current.nodes):
        raise RuntimeError(
            "Starter flow must not include JSON Output node; use GeocodeAgent → DBOutput only."
        )
    if not any(n.type == "DBOutput" for n in current.nodes):
        raise RuntimeError("Starter flow must include a DBOutput (Stylebook Output) node.")


def _assert_golden_run_result(result: object) -> None:
    """Run JSON must match slug-key executor output and include DBOutput persistence."""
    if not isinstance(result, dict):
        raise RuntimeError(f"Run result: expected object, got {type(result).__name__}")
    if "__outputKeysByNodeId" in result:
        raise RuntimeError("Run result must not include __outputKeysByNodeId")
    if "json_output" in result:
        raise RuntimeError(
            "Run result must not include json_output; canonical starter has no JSON Output node"
        )
    if "stylebook_output" not in result:
        raise RuntimeError(
            "Run result missing stylebook_output; golden path expects Stylebook Output "
            "(DBOutput) at the end of the starter flow."
        )
    so = result["stylebook_output"]
    if not isinstance(so, dict):
        raise RuntimeError("stylebook_output must be an object")
    if so.get("success") is not True:
        raise RuntimeError(f"stylebook_output.success expected True, got {so.get('success')!r}")


def _find_starter_graph(
    agate_client: httpx.Client, project_id: int
) -> tuple[str, str, dict[str, Any]]:
    graphs = agate_client.get("/graphs")
    graphs.raise_for_status()
    glist = graphs.json()
    if not isinstance(glist, list):
        raise RuntimeError(f"list graphs: expected list, got {type(glist)}")
    starter = next(
        (
            g
            for g in glist
            if isinstance(g, dict)
            and g.get("project_id") == project_id
            and g.get("name") == STARTER_FLOW_GRAPH_DISPLAY_NAME
        ),
        None,
    )
    if starter is None:
        spec = starter_geocode_flow_graph_spec()
        raise RuntimeError(
            f"Smoke needs graph named {STARTER_FLOW_GRAPH_DISPLAY_NAME!r} "
            f"on project id {project_id}. "
            "Start the stack with BACKFIELD_LOCAL_BOOTSTRAP=1 (see docker-compose) "
            f"or create it with spec name {spec.name!r}."
        )
    _assert_starter_graph_matches_bootstrap(starter)
    return str(starter["id"]), STARTER_FLOW_GRAPH_DISPLAY_NAME, starter


def run_service_bearer_flow() -> int:
    _log(
        "Smoke (service bearer): "
        f"AGATE_API_BASE={AGATE_API_BASE} STYLEBOOK_API_BASE={STYLEBOOK_API_BASE} "
        f"(Agate Bearer: {'set' if SMOKE_AGATE_BEARER else 'missing'})"
    )
    agate_headers = {"Authorization": f"Bearer {SMOKE_AGATE_BEARER}"} if SMOKE_AGATE_BEARER else {}
    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0, headers=agate_headers) as agate_client:
        _health_checks(agate_client)

        projects = agate_client.get("/projects")
        projects.raise_for_status()
        plist = projects.json()
        if not isinstance(plist, list):
            raise RuntimeError(f"list projects: expected list, got {type(plist)}")
        general = next((p for p in plist if p.get("slug") == SMOKE_PROJECT_SLUG), None)
        if general is None:
            raise RuntimeError(
                "Smoke needs the seeded 'General' project (slug general). "
                "Run migrations (agate-api entrypoint or make migrate)."
            )
        project_id = int(general["id"])

        graph_id, graph_name, _starter = _find_starter_graph(agate_client, project_id)

        run = _assert_ok(agate_client.post("/runs", json={"graph_id": graph_id}), "create run")
        terminal_run = _wait_for_terminal_run(agate_client, str(run["id"]))
        if terminal_run.get("status") != "succeeded":
            raise RuntimeError(
                "Smoke run failed: "
                f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
            )
        _assert_golden_run_result(terminal_run.get("result"))

        _log("Smoke passed (service bearer).")
        _log(f"Project: {project_id} ({SMOKE_PROJECT_SLUG})")
        _log(f"Graph: {graph_id} ({graph_name})")
        _log(f"Run: {terminal_run['id']}")
        return 0


def run_session_flow() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError(
            "Session smoke requires SMOKE_EMAIL and SMOKE_PASSWORD "
            "(and CORE_API_BASE if not using default)."
        )

    _log(
        f"Smoke (session): CORE_API_BASE={CORE_API_BASE} AGATE_API_BASE={AGATE_API_BASE} "
        f"STYLEBOOK_API_BASE={STYLEBOOK_API_BASE} workspace={SMOKE_WORKSPACE_SLUG!r} "
        f"project={SMOKE_PROJECT_SLUG!r}"
    )

    with httpx.Client(base_url=CORE_API_BASE, timeout=30.0) as core:
        core_health = _assert_ok(core.get("/health"), "Core health")
        if core_health.get("ok") is not True:
            raise RuntimeError(f"Core health failed: {core_health}")

        if os.environ.get("SMOKE_BOOTSTRAP", "").lower() in ("1", "true", "yes"):
            boot = core.post(
                "/v1/bootstrap/first-user",
                json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD},
            )
            if boot.status_code not in (200, 400):
                boot.raise_for_status()
            _log(
                "Smoke: bootstrap first-user "
                + ("ok" if boot.status_code == 200 else "skipped (users already exist)")
            )

        login = core.post(
            "/v1/auth/login",
            json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD},
        )
        login.raise_for_status()
        _log("Smoke: logged in (Core API).")

        session_token = core.cookies.get("session")
        if not session_token:
            raise RuntimeError("Login did not set session cookie; cannot continue session smoke.")

        ws_resp = core.get("/v1/me/workspaces")
        ws_resp.raise_for_status()
        ws_payload = ws_resp.json()
        if not isinstance(ws_payload, list):
            raise RuntimeError(
                f"me/workspaces: expected list, got {type(ws_payload).__name__}: {ws_payload!r}"
            )
        workspace = next((w for w in ws_payload if w.get("slug") == SMOKE_WORKSPACE_SLUG), None)
        if workspace is None:
            slugs = [w.get("slug") for w in ws_payload]
            raise RuntimeError(
                f"Workspace slug {SMOKE_WORKSPACE_SLUG!r} not in /v1/me/workspaces; have {slugs!r}"
            )
        _log(f"Smoke: opened workspace {workspace.get('name')!r} (slug={SMOKE_WORKSPACE_SLUG!r}).")

        projects_in_ws = workspace.get("projects")
        if not isinstance(projects_in_ws, list):
            raise RuntimeError("workspace.projects: expected list")
        proj_meta = next((p for p in projects_in_ws if p.get("slug") == SMOKE_PROJECT_SLUG), None)
        if proj_meta is None:
            raise RuntimeError(
                f"Project slug {SMOKE_PROJECT_SLUG!r} not listed under workspace "
                f"{SMOKE_WORKSPACE_SLUG!r}"
            )
        project_id = int(proj_meta["id"])
        _log(
            "Smoke: selected project "
            f"{proj_meta.get('name')!r} (slug={SMOKE_PROJECT_SLUG!r}, id={project_id})."
        )

    cookie_header = {"Cookie": f"session={session_token}"}
    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0, headers=cookie_header) as agate_client:
        _health_checks(agate_client)

        projects = agate_client.get("/projects")
        projects.raise_for_status()
        plist = projects.json()
        if not isinstance(plist, list):
            raise RuntimeError(f"list projects: expected list, got {type(plist)}")
        match = next((p for p in plist if p.get("slug") == SMOKE_PROJECT_SLUG), None)
        if match is None or int(match["id"]) != project_id:
            raise RuntimeError(
                "Agate /projects view does not include the same "
                f"{SMOKE_PROJECT_SLUG!r} project as Core workspaces response."
            )
        _log("Smoke: Agate project list matches session scope.")

        graph_id, graph_name, _starter = _find_starter_graph(agate_client, project_id)
        _log(f"Smoke: selected graph {graph_name!r} (id={graph_id}).")

        run = _assert_ok(agate_client.post("/runs", json={"graph_id": graph_id}), "create run")
        terminal_run = _wait_for_terminal_run(agate_client, str(run["id"]))
        if terminal_run.get("status") != "succeeded":
            raise RuntimeError(
                "Smoke run failed: "
                f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
            )
        _assert_golden_run_result(terminal_run.get("result"))

        _log("Smoke passed (session).")
        _log(f"Project: {project_id} ({SMOKE_PROJECT_SLUG})")
        _log(f"Graph: {graph_id} ({graph_name})")
        _log(f"Run: {terminal_run['id']}")
        return 0


def main() -> int:
    if SMOKE_EMAIL and SMOKE_PASSWORD:
        return run_session_flow()
    return run_service_bearer_flow()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {_http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
