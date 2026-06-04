#!/usr/bin/env python3
"""PersonExtract + DBOutput smoke (in-process by default; optional live stack).

Default mode runs ``starter_people_flow_graph_spec`` in-process with the demo corpus
text and a mocked LLM (no API keys required). Use ``--live-llm`` to call a real model
(requires ``OPENAI_API_KEY`` or another configured provider).

Use ``--via-agate-api`` to enqueue the People starter graph on a running stack
(``make up``); requires ``SMOKE_PEOPLE_GRAPH_ID`` or a graph named **People starter**
on the General project.
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
    PEOPLE_SMOKE_DEMO_TEXT,
    PEOPLE_STARTER_FLOW_GRAPH_DISPLAY_NAME,
    execute_graph,
    starter_people_flow_graph_spec,
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
SMOKE_AGATE_BEARER = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
    "SERVICE_API_TOKEN", "backfield-dev"
)
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _mock_people_json() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "John Smith",
                    "title": "Mayor",
                    "affiliation": "Chicago",
                    "public_figure": True,
                    "type": "politician",
                    "role_in_story": "Announced park initiative",
                    "nature": "official",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Mayor John Smith of Chicago announced "
                                "a new park initiative Monday."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Jane Doe",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "community member",
                    "role_in_story": "Resident supporting the plan",
                    "nature": "affected",
                    "nature_secondary_tags": ["source"],
                    "mentions": [
                        {
                            "text": "Jane Doe, a local resident, said she supports the plan.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Robert Lee",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Arrested in vandalism case",
                    "nature": "suspect",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Police arrested Robert Lee in connection "
                                "with vandalism at the site"
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Maria Garcia",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Witnessed vandalism",
                    "nature": "witness",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {"text": "Maria Garcia witnessed the incident.", "quote": False}
                    ],
                },
            ]
        }
    )


def _run_in_process(*, live_llm: bool) -> None:
    spec = starter_people_flow_graph_spec()
    if live_llm:
        out = execute_graph(spec)
    else:
        with patch(
            "agate_nodes.person_extract.node_port.call_llm",
            return_value=_mock_people_json(),
        ):
            out = execute_graph(spec)

    so = out.get("stylebook_output")
    if not isinstance(so, dict) or so.get("success") is not True:
        raise RuntimeError(f"Expected stylebook_output.success=true, got {so!r}")
    people = so.get("people")
    if not isinstance(people, list) or len(people) < 4:
        raise RuntimeError(f"Expected >=4 people, got {people!r}")
    names = {p.get("name") for p in people if isinstance(p, dict)}
    needed = {"John Smith", "Jane Doe", "Robert Lee", "Maria Garcia"}
    if not needed.issubset(names):
        raise RuntimeError(f"Missing expected names; have {sorted(names)}")
    log(
        f"in-process people smoke OK ({len(people)} people, "
        f"text len={len(PEOPLE_SMOKE_DEMO_TEXT)})"
    )


def _find_people_graph(client: httpx.Client, project_id: int) -> str:
    env_gid = os.environ.get("SMOKE_PEOPLE_GRAPH_ID", "").strip()
    if env_gid:
        return env_gid
    graphs = assert_list(client.get("/graphs"), "list graphs")
    for g in graphs:
        if (
            isinstance(g, dict)
            and g.get("project_id") == project_id
            and g.get("name") == PEOPLE_STARTER_FLOW_GRAPH_DISPLAY_NAME
        ):
            return str(g["id"])
    raise RuntimeError(
        f"No graph named {PEOPLE_STARTER_FLOW_GRAPH_DISPLAY_NAME!r}; "
        "create one from starter_people_flow_graph_spec() or set SMOKE_PEOPLE_GRAPH_ID"
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
        graph_id = _find_people_graph(client, project_id)
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
        log(f"stack people smoke OK run_id={run_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PersonExtract smoke")
    parser.add_argument("--via-agate-api", action="store_true")
    parser.add_argument("--live-llm", action="store_true")
    args = parser.parse_args()
    try:
        if args.via_agate_api:
            _run_via_agate_api(live_llm=args.live_llm)
        else:
            _run_in_process(live_llm=args.live_llm)
    except Exception as exc:
        print(f"people smoke failed: {exc}", file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(http_error_detail(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
