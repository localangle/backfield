#!/usr/bin/env python3
"""Agate-to-Stylebook handoff smoke for a live Backfield stack.

Two modes (pick automatically):

1. **Session (UI-shaped)** — when ``SMOKE_EMAIL`` and ``SMOKE_PASSWORD`` are set.
2. **Service Bearer** — otherwise, use ``SMOKE_AGATE_BEARER`` / ``SERVICE_API_TOKEN``.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from _helpers import (
    assert_list,
    assert_object,
    ensure_health,
    http_error_detail,
    log,
    login_session_context,
    session_cookie_headers,
    smoke_db_session,
    wait_for_terminal_run,
)
from agate_runtime import (
    STARTER_FLOW_GRAPH_DISPLAY_NAME,
    GraphSpec,
    starter_geocode_flow_graph_spec,
)
from backfield_db import SubstrateArticle, SubstrateLocation, SubstrateLocationMention
from sqlmodel import select

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


def _assert_golden_run_result(result: object) -> dict[str, Any]:
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
    article_id = so.get("article_id")
    if not isinstance(article_id, int) or article_id <= 0:
        raise RuntimeError(
            "stylebook_output.article_id must be a positive integer, "
            f"got {article_id!r}"
        )
    return so


def _find_starter_graph(
    agate_client: httpx.Client, project_id: int
) -> tuple[str, str, dict[str, Any]]:
    glist = assert_list(agate_client.get("/graphs"), "list graphs")
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


def _assert_stylebook_persistence_visible(
    *,
    article_id: int,
    project_slug: str,
    stylebook_headers: dict[str, str],
) -> None:
    with smoke_db_session() as session:
        article = session.get(SubstrateArticle, article_id)
        if article is None:
            raise RuntimeError(f"Persisted article {article_id} was not found in substrate_article")

        pairs = list(
            session.exec(
                select(SubstrateLocationMention, SubstrateLocation)
                .join(
                    SubstrateLocation,
                    SubstrateLocation.id == SubstrateLocationMention.location_id,
                )
                .where(
                    SubstrateLocationMention.article_id == article_id,
                    SubstrateLocationMention.deleted == False,  # noqa: E712
                )
            ).all()
        )
        linked_location = next(
            (
                location
                for _mention, location in pairs
                if location.id is not None and location.stylebook_location_canonical_id is not None
            ),
            None,
        )
        if linked_location is None or linked_location.id is None:
            raise RuntimeError(
                f"No linked substrate location found for persisted article {article_id}"
            )
        location_id = int(linked_location.id)
        canonical_id = str(linked_location.stylebook_location_canonical_id)

    with httpx.Client(
        base_url=STYLEBOOK_API_BASE,
        timeout=10.0,
        headers=stylebook_headers,
    ) as stylebook:
        linked_substrates = assert_object(
            stylebook.get(
                f"/v1/canonical-locations/{canonical_id}/linked-substrates",
                params={"project_slug": project_slug},
            ),
            "linked substrates",
        )
        substrates = linked_substrates.get("substrates")
        if not isinstance(substrates, list) or not any(
            isinstance(row, dict) and int(row.get("id", -1)) == location_id for row in substrates
        ):
            raise RuntimeError(
                "Canonical "
                f"{canonical_id} did not expose linked substrate {location_id} "
                "through Stylebook"
            )

        mentions = assert_object(
            stylebook.get(
                f"/v1/canonical-locations/{canonical_id}/mentions",
                params={"project_slug": project_slug},
            ),
            "canonical mentions",
        )
        mention_rows = mentions.get("mentions")
        if not isinstance(mention_rows, list) or not any(
            isinstance(row, dict) and int(row.get("article_id", -1)) == article_id
            for row in mention_rows
        ):
            raise RuntimeError(
                "Canonical "
                f"{canonical_id} did not expose article {article_id} "
                "through Stylebook mentions"
            )


def run_service_bearer_flow() -> int:
    log(
        "Smoke agate-stylebook-handoff (service bearer): "
        f"AGATE_API_BASE={AGATE_API_BASE} STYLEBOOK_API_BASE={STYLEBOOK_API_BASE} "
        f"(Agate Bearer: {'set' if SMOKE_AGATE_BEARER else 'missing'})"
    )
    agate_headers = {"Authorization": f"Bearer {SMOKE_AGATE_BEARER}"} if SMOKE_AGATE_BEARER else {}
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=STYLEBOOK_API_BASE,
        agate_headers=agate_headers,
        stylebook_headers=agate_headers,
    )
    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0, headers=agate_headers) as agate_client:
        plist = assert_list(agate_client.get("/projects"), "list projects")
        general = next((p for p in plist if p.get("slug") == SMOKE_PROJECT_SLUG), None)
        if general is None:
            raise RuntimeError(
                "Smoke needs the seeded 'General' project (slug general). "
                "Run migrations (agate-api entrypoint or make migrate)."
            )
        project_id = int(general["id"])

        graph_id, graph_name, _starter = _find_starter_graph(agate_client, project_id)

        run = assert_object(agate_client.post("/runs", json={"graph_id": graph_id}), "create run")
        terminal_run = wait_for_terminal_run(
            agate_client,
            str(run["id"]),
            timeout_s=POLL_TIMEOUT_SECONDS,
            interval_s=POLL_INTERVAL_SECONDS,
        )
        if terminal_run.get("status") != "succeeded":
            raise RuntimeError(
                "Smoke run failed: "
                f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
            )
        stylebook_output = _assert_golden_run_result(terminal_run.get("result"))
        _assert_stylebook_persistence_visible(
            article_id=int(stylebook_output["article_id"]),
            project_slug=SMOKE_PROJECT_SLUG,
            stylebook_headers=agate_headers,
        )

        log("Smoke agate-stylebook-handoff passed (service bearer).")
        log(f"Project: {project_id} ({SMOKE_PROJECT_SLUG})")
        log(f"Graph: {graph_id} ({graph_name})")
        log(f"Run: {terminal_run['id']}")
        return 0


def run_session_flow() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError(
            "Session smoke requires SMOKE_EMAIL and SMOKE_PASSWORD "
            "(and CORE_API_BASE if not using default)."
        )

    log(
        f"Smoke agate-stylebook-handoff (session): CORE_API_BASE={CORE_API_BASE} "
        f"AGATE_API_BASE={AGATE_API_BASE} STYLEBOOK_API_BASE={STYLEBOOK_API_BASE} "
        f"workspace={SMOKE_WORKSPACE_SLUG!r} project={SMOKE_PROJECT_SLUG!r}"
    )
    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=SMOKE_WORKSPACE_SLUG,
        project_slug=SMOKE_PROJECT_SLUG,
        bootstrap_first_user=os.environ.get("SMOKE_BOOTSTRAP", "").lower() in ("1", "true", "yes"),
    )
    project_id = ctx.project_id
    cookie_header = session_cookie_headers(ctx.session_token)
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=STYLEBOOK_API_BASE,
        core_base=CORE_API_BASE,
        agate_headers=cookie_header,
        stylebook_headers=cookie_header,
    )
    with httpx.Client(base_url=AGATE_API_BASE, timeout=10.0, headers=cookie_header) as agate_client:
        plist = assert_list(agate_client.get("/projects"), "list projects")
        match = next((p for p in plist if p.get("slug") == SMOKE_PROJECT_SLUG), None)
        if match is None or int(match["id"]) != project_id:
            raise RuntimeError(
                "Agate /projects view does not include the same "
                f"{SMOKE_PROJECT_SLUG!r} project as Core workspaces response."
            )
        log("Smoke: Agate project list matches session scope.")

        graph_id, graph_name, _starter = _find_starter_graph(agate_client, project_id)
        log(f"Smoke: selected graph {graph_name!r} (id={graph_id}).")

        run = assert_object(agate_client.post("/runs", json={"graph_id": graph_id}), "create run")
        terminal_run = wait_for_terminal_run(
            agate_client,
            str(run["id"]),
            timeout_s=POLL_TIMEOUT_SECONDS,
            interval_s=POLL_INTERVAL_SECONDS,
        )
        if terminal_run.get("status") != "succeeded":
            raise RuntimeError(
                "Smoke run failed: "
                f"status={terminal_run.get('status')} error={terminal_run.get('error_message')}"
            )
        stylebook_output = _assert_golden_run_result(terminal_run.get("result"))
        _assert_stylebook_persistence_visible(
            article_id=int(stylebook_output["article_id"]),
            project_slug=ctx.project_slug,
            stylebook_headers=cookie_header,
        )

        log("Smoke agate-stylebook-handoff passed (session).")
        log(f"Project: {project_id} ({SMOKE_PROJECT_SLUG})")
        log(f"Graph: {graph_id} ({graph_name})")
        log(f"Run: {terminal_run['id']}")
        return 0


def main() -> int:
    if SMOKE_EMAIL and SMOKE_PASSWORD:
        return run_session_flow()
    return run_service_bearer_flow()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
