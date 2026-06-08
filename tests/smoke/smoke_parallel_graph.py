#!/usr/bin/env python3
"""Parallel graph execution smoke (standalone, not part of CI).

Validates:
  1. Same-level extract nodes run concurrently when ``BACKFIELD_PARALLEL_GRAPH_LEVELS`` is on
  2. Cross-level overlap (e.g. GeocodeAgent after fast PlaceExtract while Org still runs)
  3. Multiple runs (processed items) can execute concurrently on the worker
  4. Prints timing tables for each phase

Default mode is in-process with a mocked slow LLM (no API keys, no stack).

Use ``--via-agate-api`` against a live stack (``make up``) with ``SMOKE_EMAIL`` /
``SMOKE_PASSWORD`` and LLM keys on the worker. Stack mode inspects
``backfield_ai_call_record`` overlap for level parallelism and enqueues several
runs at once for item-level parallelism.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from _helpers import (
    assert_object,
    ensure_health,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    smoke_db_session,
    wait_for_terminal_run,
)
from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph
from backfield_db import BackfieldAiCallRecord
from sqlmodel import select

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = os.environ.get(
    "COMPOSE_FILE",
    str(_REPO_ROOT / "infra" / "docker-compose.yml"),
)

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()
SMOKE_POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "300"))
SMOKE_POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))
SMOKE_PARALLEL_GRAPH_SLEEP_S = float(os.environ.get("SMOKE_PARALLEL_GRAPH_SLEEP_S", "0.25"))
SMOKE_PARALLEL_GRAPH_ORG_SLEEP_S = float(os.environ.get("SMOKE_PARALLEL_GRAPH_ORG_SLEEP_S", "0.5"))
SMOKE_PARALLEL_GRAPH_GEO_SLEEP_S = float(os.environ.get("SMOKE_PARALLEL_GRAPH_GEO_SLEEP_S", "0.25"))
SMOKE_PARALLEL_GRAPH_RUN_COUNT = int(os.environ.get("SMOKE_PARALLEL_GRAPH_RUN_COUNT", "3"))
SMOKE_PARALLEL_GRAPH_TEXT = os.environ.get(
    "SMOKE_PARALLEL_GRAPH_TEXT",
    "Mayor Jane Doe of Chicago announced that City Hall will fund a new park in Illinois.",
).strip()

EXTRACT_NODE_TYPES = frozenset(
    {"OrganizationExtract", "PersonExtract", "PlaceExtract"},
)


@dataclass(frozen=True)
class TimingRow:
    label: str
    value: float
    detail: str = ""
    unit: str = "s"


@dataclass(frozen=True)
class ExtractCallTiming:
    node_type: str
    node_id: str | None
    created_at: datetime
    latency_ms: int | None


@dataclass(frozen=True)
class ItemTiming:
    run_id: str
    item_id: int
    queued_to_done_s: float
    wall_from_batch_start_s: float


def _mock_org_json() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "City Hall",
                    "type": "government",
                    "role_in_story": "Employer",
                    "nature": "actor",
                    "nature_secondary_tags": [],
                    "mentions": [{"text": "City Hall", "quote": False}],
                }
            ]
        }
    )


def _mock_person_json() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "Jane Doe",
                    "title": "Mayor",
                    "affiliation": "City Hall",
                    "public_figure": True,
                    "type": "politician",
                    "role_in_story": "Subject",
                    "nature": "official",
                    "nature_secondary_tags": [],
                    "mentions": [{"text": "Mayor Jane Doe", "quote": False}],
                }
            ]
        }
    )


def _mock_place_json() -> str:
    return json.dumps(
        {
            "locations": [
                {
                    "original_text": "Chicago, IL",
                    "description": "Mention of Chicago",
                    "geocode_hints": "",
                    "location": "Chicago, IL",
                    "type": "city",
                    "components": {
                        "place": None,
                        "street_road": None,
                        "span": None,
                        "address": "",
                        "neighborhood": "",
                        "city": "Chicago",
                        "county": "",
                        "state": {"name": "Illinois", "abbr": "IL"},
                        "country": {"name": "United States", "abbr": "US"},
                    },
                }
            ]
        }
    )


def _fanout_graph_spec(*, text: str) -> GraphSpec:
    return GraphSpec(
        name="smoke-parallel-fanout",
        nodes=[
            NodeConfig(id="in", type="TextInput", params={"text": text}),
            NodeConfig(id="org", type="OrganizationExtract", params={}),
            NodeConfig(id="per", type="PersonExtract", params={}),
            NodeConfig(id="plc", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="in", target="org", sourceHandle="text", targetHandle="text"),
            Edge(source="in", target="per", sourceHandle="text", targetHandle="text"),
            Edge(source="in", target="plc", sourceHandle="text", targetHandle="text"),
        ],
    )


def _fanout_graph_spec_dict(*, text: str) -> dict[str, object]:
    spec = _fanout_graph_spec(text=text)
    return {
        "name": spec.name,
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "params": node.params,
                "position": {"x": 0, "y": 0},
            }
            for node in spec.nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "sourceHandle": edge.sourceHandle,
                "targetHandle": edge.targetHandle,
            }
            for edge in spec.edges
        ],
    }


def _print_timing_table(title: str, rows: list[TimingRow]) -> None:
    log("")
    log(f"=== {title} ===")
    for row in rows:
        detail = f"  ({row.detail})" if row.detail else ""
        log(f"  {row.label:<28} {row.value:7.3f}{row.unit}{detail}")


def _slow_llm_patches(sleep_s: float):
    def slow_org(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_org_json()

    def slow_person(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_person_json()

    def slow_place(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_place_json()

    return (
        patch("agate_nodes.organization_extract.node_port.call_llm", side_effect=slow_org),
        patch("agate_nodes.person_extract.node_port.call_llm", side_effect=slow_person),
        patch("agate_nodes.place_extract.node_port.call_llm", side_effect=slow_place),
    )


def _run_in_process_level_parallelism(*, sleep_s: float) -> None:
    spec = _fanout_graph_spec(text=SMOKE_PARALLEL_GRAPH_TEXT)
    patches = _slow_llm_patches(sleep_s)
    for patch_obj in patches:
        patch_obj.start()
    try:
        prev_flag = os.environ.pop("BACKFIELD_PARALLEL_GRAPH_LEVELS", None)
        try:
            t0 = time.perf_counter()
            out_seq = execute_graph(spec)
            seq_elapsed = time.perf_counter() - t0
        finally:
            if prev_flag is not None:
                os.environ["BACKFIELD_PARALLEL_GRAPH_LEVELS"] = prev_flag

        os.environ["BACKFIELD_PARALLEL_GRAPH_LEVELS"] = "1"
        t1 = time.perf_counter()
        out_par = execute_graph(spec)
        par_elapsed = time.perf_counter() - t1

        if seq_elapsed < sleep_s * 3 * 0.85:
            raise RuntimeError(
                "Sequential fan-out was faster than expected; "
                f"got {seq_elapsed:.3f}s, expected >= {sleep_s * 3 * 0.85:.3f}s"
            )
        if par_elapsed >= sleep_s * 2:
            raise RuntimeError(
                "Parallel fan-out was not faster than two serial extracts; "
                f"got {par_elapsed:.3f}s, expected < {sleep_s * 2:.3f}s"
            )
        if set(out_seq.keys()) != set(out_par.keys()):
            raise RuntimeError(f"Output keys differ: {set(out_seq)} vs {set(out_par)}")

        speedup = seq_elapsed / par_elapsed if par_elapsed > 0 else float("inf")
        _print_timing_table(
            "Level parallelism (in-process, mocked LLM)",
            [
                TimingRow(
                    "sequential",
                    seq_elapsed,
                    f"3 x {sleep_s:.2f}s extracts serially",
                ),
                TimingRow(
                    "parallel",
                    par_elapsed,
                    "org + person + place same level",
                ),
                TimingRow("speedup", speedup, "sequential / parallel", unit="x"),
            ],
        )
        log("in-process level parallelism OK")
    finally:
        for patch_obj in patches:
            patch_obj.stop()


def _fanout_with_geocode_spec(*, text: str) -> GraphSpec:
    return GraphSpec(
        name="smoke-parallel-fanout-geocode",
        nodes=[
            NodeConfig(id="in", type="TextInput", params={"text": text}),
            NodeConfig(id="org", type="OrganizationExtract", params={}),
            NodeConfig(id="plc", type="PlaceExtract", params={}),
            NodeConfig(id="geo", type="GeocodeAgent", params={}),
        ],
        edges=[
            Edge(source="in", target="org", sourceHandle="text", targetHandle="text"),
            Edge(source="in", target="plc", sourceHandle="text", targetHandle="text"),
            Edge(source="plc", target="geo", sourceHandle="locations", targetHandle="locations"),
        ],
    )


def _run_in_process_cross_level_parallelism(
    *,
    org_sleep_s: float,
    geo_sleep_s: float,
    place_sleep_s: float,
) -> None:
    spec = _fanout_with_geocode_spec(text=SMOKE_PARALLEL_GRAPH_TEXT)

    def slow_org(*_a, **_k):
        time.sleep(org_sleep_s)
        return _mock_org_json()

    def fast_place(*_a, **_k):
        time.sleep(place_sleep_s)
        return _mock_place_json()

    async def slow_geocode(*_a, **_k):
        await asyncio.sleep(geo_sleep_s)
        return {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [{"id": "smoke-city", "name": "Chicago"}],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            }
        }

    os.environ["BACKFIELD_PARALLEL_GRAPH_LEVELS"] = "1"
    t0 = time.perf_counter()
    with (
        patch(
            "agate_nodes.organization_extract.node_port.call_llm",
            side_effect=slow_org,
        ),
        patch("agate_nodes.place_extract.node_port.call_llm", side_effect=fast_place),
        patch(
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
            side_effect=slow_geocode,
        ),
    ):
        out = execute_graph(spec)
    elapsed = time.perf_counter() - t0

    level_barrier_lower_bound = org_sleep_s + geo_sleep_s
    if elapsed >= level_barrier_lower_bound * 0.9:
        raise RuntimeError(
            "Geocode did not overlap slow OrganizationExtract; "
            f"got {elapsed:.3f}s, expected < {level_barrier_lower_bound * 0.9:.3f}s"
        )
    if "geocode_agent" not in out:
        raise RuntimeError(f"Expected geocode_agent output, got keys {sorted(out)}")

    _print_timing_table(
        "Cross-level overlap (in-process, mocked LLM)",
        [
            TimingRow(
                "ready_parallel_wall",
                elapsed,
                "geo starts after fast place, not slow org",
            ),
            TimingRow(
                "level_barrier_lower_bound",
                level_barrier_lower_bound,
                "org_sleep + geo_sleep if serialized by level",
            ),
        ],
    )
    log("in-process cross-level overlap OK")


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _extract_level_metrics(records: list[ExtractCallTiming]) -> dict[str, object]:
    if len(records) < 2:
        return {
            "record_count": len(records),
            "parallel_likely": False,
            "reason": "need at least two extract LLM records",
        }

    created = [_coerce_utc(row.created_at) for row in records]
    span_s = (max(created) - min(created)).total_seconds()
    sum_latency_s = sum((row.latency_ms or 0) for row in records) / 1000.0
    parallel_likely = sum_latency_s > 0 and span_s < sum_latency_s * 0.55
    return {
        "record_count": len(records),
        "span_s": span_s,
        "sum_latency_s": sum_latency_s,
        "parallel_likely": parallel_likely,
    }


def _fetch_extract_call_timings(
    *,
    run_id: str,
    processed_item_id: int,
) -> list[ExtractCallTiming]:
    with smoke_db_session() as session:
        rows = session.exec(
            select(BackfieldAiCallRecord)
            .where(BackfieldAiCallRecord.run_id == run_id)
            .where(BackfieldAiCallRecord.processed_item_id == processed_item_id)
            .where(BackfieldAiCallRecord.status == "succeeded")
            .where(BackfieldAiCallRecord.node_type.in_(sorted(EXTRACT_NODE_TYPES)))
            .order_by(BackfieldAiCallRecord.created_at)
        ).all()
    return [
        ExtractCallTiming(
            node_type=str(row.node_type or ""),
            node_id=row.node_id,
            created_at=_coerce_utc(row.created_at),
            latency_ms=row.latency_ms,
        )
        for row in rows
        if row.node_type in EXTRACT_NODE_TYPES
    ]


def _processed_item_id_from_terminal(terminal: dict[str, object]) -> int:
    processed_items = terminal.get("processed_items")
    if isinstance(processed_items, list) and processed_items:
        first = processed_items[0]
        if isinstance(first, dict) and isinstance(first.get("id"), int):
            return int(first["id"])
    result = terminal.get("result")
    if isinstance(result, dict):
        result_items = result.get("items")
        if isinstance(result_items, list) and result_items:
            first = result_items[0]
            if isinstance(first, dict) and isinstance(first.get("id"), int):
                return int(first["id"])
    raise RuntimeError(f"Terminal run missing processed item id: {terminal!r}")


def _item_duration_s(item_detail: dict[str, object]) -> float:
    created_at = item_detail.get("created_at")
    updated_at = item_detail.get("updated_at")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise RuntimeError(f"Processed item missing timestamps: {item_detail!r}")
    start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return max(0.0, (end - start).total_seconds())


def _log_worker_parallel_flag() -> None:
    try:
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                _COMPOSE_FILE,
                "exec",
                "-T",
                "worker",
                "printenv",
                "BACKFIELD_PARALLEL_GRAPH_LEVELS",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"worker env check skipped ({exc})")
        return

    value = (proc.stdout or "").strip()
    if proc.returncode != 0 or not value:
        log(
            "warning: could not read BACKFIELD_PARALLEL_GRAPH_LEVELS from worker; "
            "level overlap assertions may fail if sequential mode is enabled"
        )
        return
    log(f"worker BACKFIELD_PARALLEL_GRAPH_LEVELS={value!r}")


def _create_fanout_graph(client: httpx.Client, *, project_id: int) -> str:
    graph_name = f"Smoke parallel fanout {uuid.uuid4().hex[:8]}"
    graph = assert_object(
        client.post(
            "/graphs",
            json={
                "name": graph_name,
                "project_id": project_id,
                "spec": _fanout_graph_spec_dict(text=SMOKE_PARALLEL_GRAPH_TEXT),
            },
        ),
        "create fan-out graph",
    )
    return str(graph["id"])


def _run_single_stack_item(
    *,
    graph_id: str,
    batch_start: float,
    headers: dict[str, str],
) -> ItemTiming:
    with httpx.Client(base_url=AGATE_API_BASE, timeout=120.0, headers=headers) as client:
        return _run_single_stack_item_with_client(
            client,
            graph_id=graph_id,
            batch_start=batch_start,
        )


def _run_single_stack_item_with_client(
    client: httpx.Client,
    *,
    graph_id: str,
    batch_start: float,
) -> ItemTiming:
    run = assert_object(client.post("/runs", json={"graph_id": graph_id}), "create run")
    run_id = str(run["id"])
    terminal = wait_for_terminal_run(
        client,
        run_id,
        timeout_s=SMOKE_POLL_TIMEOUT_SECONDS,
        interval_s=SMOKE_POLL_INTERVAL_SECONDS,
    )
    if terminal.get("status") != "succeeded":
        raise RuntimeError(
            f"Run {run_id} failed: status={terminal.get('status')} "
            f"error={terminal.get('error_message')}"
        )

    item_id = _processed_item_id_from_terminal(terminal)
    item_detail = assert_object(
        client.get(f"/runs/{run_id}/items/{item_id}"),
        f"processed item {item_id}",
    )
    done_at = time.perf_counter()
    return ItemTiming(
        run_id=run_id,
        item_id=item_id,
        queued_to_done_s=_item_duration_s(item_detail),
        wall_from_batch_start_s=done_at - batch_start,
    )


def _run_via_agate_api(*, concurrent_runs: int) -> None:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError("stack mode requires SMOKE_EMAIL and SMOKE_PASSWORD")

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
    _log_worker_parallel_flag()

    graph_id: str | None = None
    level_item: ItemTiming | None = None
    batch_items: list[ItemTiming] = []

    with httpx.Client(base_url=AGATE_API_BASE, timeout=120.0, headers=headers) as agate:
        try:
            graph_id = _create_fanout_graph(agate, project_id=ctx.project_id)

            log("enqueueing single fan-out run for level timing")
            batch_start = time.perf_counter()
            level_item = _run_single_stack_item_with_client(
                agate,
                graph_id=graph_id,
                batch_start=batch_start,
            )

            records = _fetch_extract_call_timings(
                run_id=level_item.run_id,
                processed_item_id=level_item.item_id,
            )
            metrics = _extract_level_metrics(records)

            log("")
            log("=== Level parallelism (stack, LLM call records) ===")
            for record in records:
                latency_s = (record.latency_ms or 0) / 1000.0
                log(
                    f"  {record.node_type:<22} node={record.node_id or '-':<4} "
                    f"created={record.created_at.isoformat()} latency={latency_s:.3f}s"
                )
            log(
                f"  completion_span={metrics.get('span_s', 'n/a')}s "
                f"sum_latency={metrics.get('sum_latency_s', 'n/a')}s "
                f"parallel_likely={metrics.get('parallel_likely')}"
            )
            if metrics.get("parallel_likely") is not True:
                raise RuntimeError(
                    "Extract LLM completions look sequential on the worker; "
                    "confirm BACKFIELD_PARALLEL_GRAPH_LEVELS=1 and retry"
                )

            _print_timing_table(
                "Single item (stack)",
                [
                    TimingRow(
                        "queued_to_done",
                        level_item.queued_to_done_s,
                        detail=f"run_id={level_item.run_id}",
                    ),
                ],
            )

            log("")
            log(f"enqueueing {concurrent_runs} runs concurrently for item parallelism")
            batch_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent_runs) as pool:
                futures = [
                    pool.submit(
                        _run_single_stack_item,
                        graph_id=graph_id,
                        batch_start=batch_start,
                        headers=headers,
                    )
                    for _ in range(concurrent_runs)
                ]
                for future in as_completed(futures):
                    batch_items.append(future.result())

            batch_wall_s = time.perf_counter() - batch_start
            sum_item_s = sum(item.queued_to_done_s for item in batch_items)
            max_item_s = max(item.queued_to_done_s for item in batch_items)
            parallelism_ratio = sum_item_s / batch_wall_s if batch_wall_s > 0 else 0.0

            log("")
            log("=== Multi-item parallelism (stack) ===")
            for item in sorted(batch_items, key=lambda row: row.wall_from_batch_start_s):
                log(
                    f"  run={item.run_id} item={item.item_id} "
                    f"queued_to_done={item.queued_to_done_s:.3f}s "
                    f"wall_from_batch_start={item.wall_from_batch_start_s:.3f}s"
                )
            _print_timing_table(
                "Batch summary",
                [
                    TimingRow(
                        "batch_wall",
                        batch_wall_s,
                        detail=f"{concurrent_runs} concurrent runs",
                    ),
                    TimingRow("sum_item_queued_to_done", sum_item_s),
                    TimingRow("max_item_queued_to_done", max_item_s),
                    TimingRow(
                        "parallelism_ratio",
                        parallelism_ratio,
                        detail="sum_item / batch_wall",
                        unit="x",
                    ),
                ],
            )

            if parallelism_ratio < 1.25:
                raise RuntimeError(
                    "Concurrent runs did not overlap enough on the worker; "
                    f"parallelism_ratio={parallelism_ratio:.2f} (expected >= 1.25)"
                )
            log("stack parallel graph smoke OK")
        finally:
            if graph_id and not keep_smoke_data():
                with suppress(Exception):
                    agate.delete(f"/graphs/{graph_id}").raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel graph execution smoke (not CI)")
    parser.add_argument(
        "--via-agate-api",
        action="store_true",
        help="Also run live-stack timing (requires make up, session creds, LLM keys)",
    )
    parser.add_argument(
        "--concurrent-runs",
        type=int,
        default=SMOKE_PARALLEL_GRAPH_RUN_COUNT,
        help="Concurrent runs for stack multi-item phase",
    )
    args = parser.parse_args()

    try:
        _run_in_process_level_parallelism(sleep_s=SMOKE_PARALLEL_GRAPH_SLEEP_S)
        _run_in_process_cross_level_parallelism(
            org_sleep_s=SMOKE_PARALLEL_GRAPH_ORG_SLEEP_S,
            geo_sleep_s=SMOKE_PARALLEL_GRAPH_GEO_SLEEP_S,
            place_sleep_s=min(0.05, SMOKE_PARALLEL_GRAPH_SLEEP_S / 5),
        )
        if args.via_agate_api:
            if args.concurrent_runs < 2:
                raise RuntimeError("--concurrent-runs must be >= 2 for stack multi-item phase")
            _run_via_agate_api(concurrent_runs=args.concurrent_runs)
    except Exception as exc:
        print(f"parallel graph smoke failed: {exc}", file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(http_error_detail(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
