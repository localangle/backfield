#!/usr/bin/env python3
"""OrganizationExtract + DBOutput smoke (in-process by default; optional live stack).

Default mode runs ``starter_organizations_flow_graph_spec`` in-process with the demo corpus
text and a mocked LLM (no API keys required). Use ``--live-llm`` to call a real model.

Use ``--via-agate-api`` to enqueue the Organizations starter graph on a running stack
(``make up``); requires ``SMOKE_ORGANIZATIONS_GRAPH_ID`` or a graph named **Organizations starter**
on the General project (local bootstrap does not create this graph).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from unittest.mock import patch

import httpx
from _helpers import (
    assert_list,
    assert_object,
    ensure_health,
    http_error_detail,
    log,
    resolve_run_execution_output,
    wait_for_terminal_run,
)
from agate_runtime import (
    ORGANIZATIONS_SMOKE_DEMO_TEXT,
    ORGANIZATIONS_STARTER_FLOW_GRAPH_DISPLAY_NAME,
    execute_graph,
    starter_organizations_flow_graph_spec,
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
SMOKE_AGATE_BEARER = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
    "SERVICE_API_TOKEN", "backfield-dev"
)
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _mock_organizations_json() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "Chicago City Hall",
                    "type": "government",
                    "role_in_story": "Announced park initiative",
                    "nature": "actor",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Chicago City Hall announced a new park initiative Monday."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Police Department",
                    "type": "law_enforcement",
                    "role_in_story": "Will increase patrols",
                    "nature": "regulator",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "The Chicago Police Department said it will increase "
                                "patrols near the site."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Cook County",
                    "type": "government",
                    "role_in_story": "Approved funding",
                    "nature": "source",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Cook County approved funding for the project.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Cubs",
                    "type": "sports_team",
                    "role_in_story": "Hosted ribbon-cutting",
                    "nature": "context",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "The Chicago Cubs hosted a ribbon-cutting at Wrigley Field."
                            ),
                            "quote": False,
                        }
                    ],
                },
            ]
        }
    )


def _run_in_process(*, live_llm: bool) -> None:
    spec = starter_organizations_flow_graph_spec()
    if live_llm:
        out = execute_graph(spec)
    else:
        with patch(
            "agate_nodes.organization_extract.node_port.call_llm",
            return_value=_mock_organizations_json(),
        ):
            out = execute_graph(spec)

    so = out.get("stylebook_output")
    if not isinstance(so, dict) or so.get("success") is not True:
        raise RuntimeError(f"Expected stylebook_output.success=true, got {so!r}")
    organizations = so.get("organizations")
    if not isinstance(organizations, list) or len(organizations) < 4:
        raise RuntimeError(f"Expected >=4 organizations, got {organizations!r}")
    names = {o.get("name") for o in organizations if isinstance(o, dict)}
    needed = {
        "Chicago City Hall",
        "Chicago Police Department",
        "Cook County",
        "Chicago Cubs",
    }
    if not needed.issubset(names):
        raise RuntimeError(f"Missing expected names; have {sorted(names)}")
    log(
        f"in-process organizations smoke OK ({len(organizations)} organizations, "
        f"text len={len(ORGANIZATIONS_SMOKE_DEMO_TEXT)})"
    )


def _find_organizations_graph(client: httpx.Client, project_id: int) -> str:
    env_gid = os.environ.get("SMOKE_ORGANIZATIONS_GRAPH_ID", "").strip()
    if env_gid:
        return env_gid
    graphs = assert_list(client.get("/graphs"), "list graphs")
    for g in graphs:
        if (
            isinstance(g, dict)
            and g.get("project_id") == project_id
            and g.get("name") == ORGANIZATIONS_STARTER_FLOW_GRAPH_DISPLAY_NAME
        ):
            return str(g["id"])
    raise RuntimeError(
        f"No graph named {ORGANIZATIONS_STARTER_FLOW_GRAPH_DISPLAY_NAME!r}; "
        "create one from starter_organizations_flow_graph_spec() or set "
        "SMOKE_ORGANIZATIONS_GRAPH_ID"
    )


def _run_via_agate_api(*, live_llm: bool) -> None:
    headers = {"Authorization": f"Bearer {SMOKE_AGATE_BEARER}"}
    with httpx.Client(base_url=AGATE_API_BASE, headers=headers, timeout=120.0) as client:
        ensure_health(client, label="agate-api")
        projects = assert_list(client.get("/projects"), "projects")
        project = next(
            (p for p in projects if isinstance(p, dict) and p.get("slug") == SMOKE_PROJECT_SLUG),
            None,
        )
        if project is None:
            raise RuntimeError(f"Project slug {SMOKE_PROJECT_SLUG!r} not found")
        project_id = int(project["id"])
        graph_id = _find_organizations_graph(client, project_id)
        payload: dict[str, object] = {"graph_id": graph_id}
        if not live_llm:
            log("live LLM disabled; stack mode still runs real extract on starter graph text")
        run = assert_object(client.post("/runs", json=payload), "create run")
        run_id = str(run["id"])
        terminal = wait_for_terminal_run(client, run_id)
        execution_output = resolve_run_execution_output(client, terminal)
        so = execution_output.get("stylebook_output")
        if not isinstance(so, dict) or so.get("success") is not True:
            raise RuntimeError(f"stylebook_output.success expected true, got {so!r}")
        log(f"stack organizations smoke OK run_id={run_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="OrganizationExtract smoke")
    parser.add_argument("--via-agate-api", action="store_true")
    parser.add_argument("--live-llm", action="store_true")
    args = parser.parse_args()
    try:
        if args.via_agate_api:
            _run_via_agate_api(live_llm=args.live_llm)
        else:
            _run_in_process(live_llm=args.live_llm)
    except Exception as exc:
        print(f"organizations smoke failed: {exc}", file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(http_error_detail(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
