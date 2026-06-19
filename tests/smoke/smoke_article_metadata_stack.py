#!/usr/bin/env python3
"""ArticleMetadata + DBOutput smoke (in-process by default; optional live stack).

Default mode runs ``starter_article_metadata_flow_graph_spec`` in-process with the demo
corpus text and a mocked LLM (no API keys required). Use ``--live-llm`` to call a real
model (requires ``OPENAI_API_KEY`` or another configured provider).

Use ``--via-agate-api`` to enqueue the Article Metadata starter graph on a running stack
(``make up``); requires ``SMOKE_ARTICLE_METADATA_GRAPH_ID`` or a graph named
**Article Metadata starter** on the General project (local bootstrap does not create this
graph).
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
    ARTICLE_METADATA_SMOKE_DEMO_TEXT,
    ARTICLE_METADATA_STARTER_FLOW_GRAPH_DISPLAY_NAME,
    execute_graph,
    starter_article_metadata_flow_graph_spec,
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
SMOKE_AGATE_BEARER = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
    "SERVICE_API_TOKEN", "backfield-dev"
)
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _mock_article_metadata_json() -> str:
    return json.dumps(
        {
            "subject": "government_action",
            "rationale": "City council vote on a neighborhood park.",
            "confidence": 0.82,
        }
    )


def _assert_stylebook_article_metadata(so: object) -> None:
    if not isinstance(so, dict) or so.get("success") is not True:
        raise RuntimeError(f"Expected stylebook_output.success=true, got {so!r}")
    meta = so.get("article_metadata")
    if not isinstance(meta, dict):
        raise RuntimeError(f"Expected article_metadata dict, got {meta!r}")
    if meta.get("meta_type") != "subject":
        raise RuntimeError(f"Expected meta_type=subject, got {meta.get('meta_type')!r}")
    category = meta.get("category")
    if not isinstance(category, str) or not category.strip():
        raise RuntimeError(f"Expected non-empty category, got {category!r}")


def _run_in_process(*, live_llm: bool) -> None:
    spec = starter_article_metadata_flow_graph_spec()
    if live_llm:
        out = execute_graph(spec)
    else:
        with patch(
            "agate_nodes.article_metadata.node_port.call_llm",
            return_value=_mock_article_metadata_json(),
        ):
            out = execute_graph(spec)

    _assert_stylebook_article_metadata(out.get("stylebook_output"))
    log(
        "in-process article metadata smoke OK "
        f"(category={out['stylebook_output']['article_metadata']['category']!r}, "
        f"text len={len(ARTICLE_METADATA_SMOKE_DEMO_TEXT)})"
    )


def _find_article_metadata_graph(client: httpx.Client, project_id: int) -> str:
    env_gid = os.environ.get("SMOKE_ARTICLE_METADATA_GRAPH_ID", "").strip()
    if env_gid:
        return env_gid
    graphs = assert_list(client.get("/graphs"), "list graphs")
    for g in graphs:
        if (
            isinstance(g, dict)
            and g.get("project_id") == project_id
            and g.get("name") == ARTICLE_METADATA_STARTER_FLOW_GRAPH_DISPLAY_NAME
        ):
            return str(g["id"])
    raise RuntimeError(
        f"No graph named {ARTICLE_METADATA_STARTER_FLOW_GRAPH_DISPLAY_NAME!r}; "
        "create one from starter_article_metadata_flow_graph_spec() or set "
        "SMOKE_ARTICLE_METADATA_GRAPH_ID"
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
        graph_id = _find_article_metadata_graph(client, project_id)
        payload: dict[str, object] = {"graph_id": graph_id}
        if not live_llm:
            log("live LLM disabled; stack mode still runs real extract on starter graph text")
        run = assert_object(client.post("/runs", json=payload), "create run")
        run_id = str(run["id"])
        terminal = wait_for_terminal_run(client, run_id)
        execution_output = resolve_run_execution_output(client, terminal)
        _assert_stylebook_article_metadata(execution_output.get("stylebook_output"))
        log(f"stack article metadata smoke OK run_id={run_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ArticleMetadata smoke")
    parser.add_argument("--via-agate-api", action="store_true")
    parser.add_argument("--live-llm", action="store_true")
    args = parser.parse_args()
    try:
        if args.via_agate_api:
            _run_via_agate_api(live_llm=args.live_llm)
        else:
            _run_in_process(live_llm=args.live_llm)
    except Exception as exc:
        print(f"article metadata smoke failed: {exc}", file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(http_error_detail(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
