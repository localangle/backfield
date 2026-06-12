#!/usr/bin/env python3
"""CustomExtract + DBOutput smoke (in-process by default; optional live stack).

Default mode runs ``starter_custom_extract_flow_graph_spec`` in-process with the demo
recipe article and a mocked LLM (no API keys required). Use ``--live-llm`` to call a
real model (requires ``OPENAI_API_KEY`` or another configured provider).

Use ``--via-agate-api`` to enqueue the Custom Extract starter graph on a running stack
(``make up``); requires ``SMOKE_CUSTOM_EXTRACT_GRAPH_ID`` or a graph named
**Custom Extract starter** on the General project (local bootstrap does not create this
graph). Stack mode also asserts ``substrate_custom_record`` rows exist for the article.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from unittest.mock import patch

import httpx
from _helpers import (
    assert_list,
    assert_object,
    http_error_detail,
    log,
    resolve_run_execution_output,
    smoke_db_session,
    wait_for_terminal_run,
)
from agate_runtime import (
    CUSTOM_EXTRACT_SMOKE_DEMO_TEXT,
    CUSTOM_EXTRACT_STARTER_FLOW_GRAPH_DISPLAY_NAME,
    execute_graph,
    starter_custom_extract_flow_graph_spec,
)
from backfield_db import SubstrateCustomRecord
from sqlmodel import select

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
SMOKE_AGATE_BEARER = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
    "SERVICE_API_TOKEN", "backfield-dev"
)
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()
POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))


def _mock_custom_extract_json() -> str:
    """Grounded ingredient records plus one ungrounded row (exercises drop counting)."""
    return json.dumps(
        {
            "records": [
                {
                    "fields": {"name": "flour", "quantity": "two cups"},
                    "mentions": [{"text": "two cups of flour", "quote": False}],
                    "confidence": 0.95,
                },
                {
                    "fields": {"name": "baking soda", "quantity": "one teaspoon"},
                    "mentions": [{"text": "one teaspoon of baking soda", "quote": False}],
                    "confidence": 0.9,
                },
                {
                    "fields": {"name": "salt", "quantity": "a pinch"},
                    "mentions": [{"text": "a pinch of salt", "quote": False}],
                },
                {
                    "fields": {"name": "vanilla extract", "quantity": "unknown"},
                    "mentions": [],
                },
            ]
        }
    )


def _assert_custom_records_block(so: object, *, expect_dropped: int | None) -> dict[str, Any]:
    """Run JSON must include the ingredients record set with schema + grounded records."""
    if not isinstance(so, dict) or so.get("success") is not True:
        raise RuntimeError(f"Expected stylebook_output.success=true, got {so!r}")
    block = so.get("custom_records")
    if not isinstance(block, dict):
        raise RuntimeError(f"Expected custom_records dict, got {block!r}")
    ingredients = block.get("ingredients")
    if not isinstance(ingredients, dict):
        raise RuntimeError(f"Expected custom_records.ingredients dict, got {ingredients!r}")

    schema = ingredients.get("schema")
    if not isinstance(schema, list) or {spec.get("name") for spec in schema} != {
        "name",
        "quantity",
    }:
        raise RuntimeError(f"Expected ingredients schema with name+quantity fields, got {schema!r}")

    records = ingredients.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"Expected non-empty ingredients records list, got {records!r}")
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(f"Record must be an object, got {record!r}")
        if not isinstance(record.get("key"), str) or not record["key"]:
            raise RuntimeError(f"Record missing stable key: {record!r}")
        if not isinstance(record.get("fields"), dict) or not record["fields"]:
            raise RuntimeError(f"Record missing fields: {record!r}")
        mentions = record.get("mentions")
        if not isinstance(mentions, list) or not mentions:
            raise RuntimeError(f"Record must be grounded by at least one mention: {record!r}")

    dropped = ingredients.get("dropped_ungrounded")
    if not isinstance(dropped, int):
        raise RuntimeError(f"Expected integer dropped_ungrounded, got {dropped!r}")
    if expect_dropped is not None and dropped != expect_dropped:
        raise RuntimeError(f"Expected dropped_ungrounded={expect_dropped}, got {dropped}")
    return ingredients


def _assert_substrate_rows(article_id: int) -> int:
    with smoke_db_session() as session:
        rows = list(
            session.exec(
                select(SubstrateCustomRecord).where(
                    SubstrateCustomRecord.article_id == article_id,
                    SubstrateCustomRecord.record_type == "ingredients",
                )
            ).all()
        )
    if not rows:
        raise RuntimeError(
            f"No substrate_custom_record rows for article {article_id} record_type=ingredients"
        )
    return len(rows)


def _run_in_process(*, live_llm: bool) -> None:
    spec = starter_custom_extract_flow_graph_spec()
    if live_llm:
        out = execute_graph(spec)
    else:
        with patch(
            "agate_nodes.custom_extract.node_port.call_llm",
            return_value=_mock_custom_extract_json(),
        ):
            out = execute_graph(spec)

    ingredients = _assert_custom_records_block(
        out.get("stylebook_output"),
        expect_dropped=None if live_llm else 1,
    )
    log(
        "in-process custom extract smoke OK "
        f"(records={len(ingredients['records'])}, "
        f"dropped_ungrounded={ingredients['dropped_ungrounded']}, "
        f"text len={len(CUSTOM_EXTRACT_SMOKE_DEMO_TEXT)})"
    )


def _find_custom_extract_graph(client: httpx.Client, project_id: int) -> str:
    env_gid = os.environ.get("SMOKE_CUSTOM_EXTRACT_GRAPH_ID", "").strip()
    if env_gid:
        return env_gid
    graphs = assert_list(client.get("/graphs"), "list graphs")
    for g in graphs:
        if (
            isinstance(g, dict)
            and g.get("project_id") == project_id
            and g.get("name") == CUSTOM_EXTRACT_STARTER_FLOW_GRAPH_DISPLAY_NAME
        ):
            return str(g["id"])
    raise RuntimeError(
        f"No graph named {CUSTOM_EXTRACT_STARTER_FLOW_GRAPH_DISPLAY_NAME!r}; "
        "create one from starter_custom_extract_flow_graph_spec() or set "
        "SMOKE_CUSTOM_EXTRACT_GRAPH_ID"
    )


def _run_via_agate_api(*, live_llm: bool) -> None:
    headers = {"Authorization": f"Bearer {SMOKE_AGATE_BEARER}"}
    with httpx.Client(base_url=AGATE_API_BASE, headers=headers, timeout=120.0) as client:
        health = assert_object(client.get("/health"), "agate-api health")
        if health.get("ok") is not True:
            raise RuntimeError(f"agate-api health failed: {health}")
        projects = assert_list(client.get("/projects"), "projects")
        project = next(
            (p for p in projects if isinstance(p, dict) and p.get("slug") == SMOKE_PROJECT_SLUG),
            None,
        )
        if project is None:
            raise RuntimeError(f"Project slug {SMOKE_PROJECT_SLUG!r} not found")
        project_id = int(project["id"])
        graph_id = _find_custom_extract_graph(client, project_id)
        payload: dict[str, object] = {"graph_id": graph_id}
        if not live_llm:
            log("live LLM disabled; stack mode still runs real extract on starter graph text")
        run = assert_object(client.post("/runs", json=payload), "create run")
        run_id = str(run["id"])
        terminal = wait_for_terminal_run(
            client,
            run_id,
            timeout_s=POLL_TIMEOUT_SECONDS,
            interval_s=POLL_INTERVAL_SECONDS,
        )
        if terminal.get("status") != "succeeded":
            raise RuntimeError(
                "Smoke run failed: "
                f"status={terminal.get('status')} error={terminal.get('error_message')}"
            )
        execution_output = resolve_run_execution_output(client, terminal)
        stylebook_output = execution_output.get("stylebook_output")
        _assert_custom_records_block(stylebook_output, expect_dropped=None)

        article_id = (
            stylebook_output.get("article_id") if isinstance(stylebook_output, dict) else None
        )
        if not isinstance(article_id, int) or article_id <= 0:
            raise RuntimeError(f"Expected positive stylebook_output.article_id, got {article_id!r}")
        row_count = _assert_substrate_rows(article_id)
        log(
            f"stack custom extract smoke OK run_id={run_id} "
            f"article_id={article_id} substrate_rows={row_count}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="CustomExtract smoke")
    parser.add_argument("--via-agate-api", action="store_true")
    parser.add_argument("--live-llm", action="store_true")
    args = parser.parse_args()
    try:
        if args.via_agate_api:
            _run_via_agate_api(live_llm=args.live_llm)
        else:
            _run_in_process(live_llm=args.live_llm)
    except Exception as exc:
        print(f"custom extract smoke failed: {exc}", file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(http_error_detail(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
