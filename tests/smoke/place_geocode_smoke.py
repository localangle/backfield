#!/usr/bin/env python3
"""PlaceExtract + GeocodeAgent smoke (manual / local; not part of ``make test``).

**Default (in-process):** loads ``fixtures/place_geocode_corpus.json``, runs PlaceExtract then
one GeocodeAgent pass per scenario (same keys as worker), prints a scoreboard and
appends one JSON line per scenario to ``artifacts/place_geocode_smoke_history.jsonl``.

**``--via-agate-api``:** health-check Agate + Stylebook, then ``POST /runs`` for the graph id
from ``SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID``, or the General project's **Starter flow** graph when
that env var is unset (same graph as ``make smoke`` — Starter flow uses GeocodeAgent).

Environment (in-process uses repo-root ``.env`` like ``golden_path_stack.py``):

- ``OPENAI_API_KEY`` (required for PlaceExtract + GeocodeAgent)
- ``PELIAS_API_KEY``, optional ``BRAVE_SEARCH_API_KEY``, ``GEOCODIO_API_KEY``
- ``SMOKE_PLACE_GEOCODE_CORPUS`` — path to JSON corpus (default: beside this script)
- ``SMOKE_PLACE_GEOCODE_HISTORY`` — JSONL path (default under ``tests/smoke/artifacts/``)

Stack mode additionally uses ``AGATE_API_BASE``, ``STYLEBOOK_API_BASE``, ``SERVICE_API_TOKEN`` /
``SMOKE_AGATE_BEARER``, ``SMOKE_PROJECT_SLUG`` (same as golden-path smoke).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from _helpers import (
    assert_list,
    assert_object,
    ensure_health,
    http_error_detail,
    log,
    wait_for_terminal_run,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE_DIR = Path(__file__).resolve().parent
_DEFAULT_CORPUS = _SMOKE_DIR / "fixtures" / "place_geocode_corpus.json"
_DEFAULT_HISTORY = _SMOKE_DIR / "artifacts" / "place_geocode_smoke_history.jsonl"


def _load_corpus(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key in ("scenarios", "integration"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("id") and item.get("text"):
                merged = {**defaults, **item}
                merged["_section"] = key
                rows.append(merged)
    if not rows:
        raise RuntimeError(f"No scenarios in corpus: {path}")
    return rows


def _extract_types(locations: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for loc in locations:
        loc_info = loc.get("location") or {}
        t = loc_info.get("type")
        if isinstance(t, str) and t.strip():
            out.add(t.strip().lower())
    return out


def _check_expect_types(found: set[str], expect: list[str] | None) -> tuple[bool, str]:
    if not expect:
        return True, ""
    missing = [t for t in expect if t.lower() not in found]
    if missing:
        return False, f"missing types: {missing} (found {sorted(found)})"
    return True, ""


def _places_totals(places: dict[str, Any]) -> tuple[int, int]:
    """Return (resolved-ish count, needs_review count)."""
    nr = places.get("needs_review") if isinstance(places.get("needs_review"), list) else []
    n_review = len(nr)
    n_res = 0
    areas = places.get("areas") if isinstance(places.get("areas"), dict) else {}
    for _k, bucket in areas.items():
        if isinstance(bucket, list):
            n_res += len(bucket)
    pts = places.get("points") if isinstance(places.get("points"), list) else []
    n_res += len(pts)
    return n_res, n_review


def _run_in_process_scenario(
    row: dict[str, Any],
    *,
    ctx: Any,
    geocode_params: dict[str, Any],
) -> dict[str, Any]:
    from agate_runtime.runners import (
        run_geocode_agent_runtime,
        run_place_extract_runtime,
    )

    text = str(row["text"])
    scenario_id = str(row["id"])

    t0 = time.perf_counter()
    extract_out = run_place_extract_runtime(
        params={"model": row.get("model", "gpt-4o-mini")},
        input_state={"text": text},
        ctx=ctx,
    )
    extract_s = time.perf_counter() - t0

    locations = extract_out.get("locations")
    if not isinstance(locations, list):
        locations = []

    found_types = _extract_types(locations)
    expect = row.get("expect_types")
    expect_list = expect if isinstance(expect, list) else None
    extract_ok, extract_note = _check_expect_types(found_types, expect_list)

    t1 = time.perf_counter()
    err: str | None = None
    geocode_out: dict[str, Any] = {}
    try:
        merged_in = {**extract_out, "text": text}
        geocode_out = run_geocode_agent_runtime(
            params=geocode_params,
            input_state=merged_in,
            ctx=ctx,
        )
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc!r}"
    geocode_s = time.perf_counter() - t1

    places = geocode_out.get("places") if isinstance(geocode_out.get("places"), dict) else {}
    n_res, n_rev = _places_totals(places)
    geocode_ok = err is None and n_res > 0 and n_rev == 0
    partial = err is None and n_res > 0 and n_rev > 0

    return {
        "scenario_id": scenario_id,
        "section": row.get("_section", ""),
        "extract_s": round(extract_s, 3),
        "geocode_s": round(geocode_s, 3),
        "extract_ok": extract_ok,
        "extract_note": extract_note,
        "types_found": sorted(found_types),
        "locations_n": len(locations),
        "resolved_n": n_res,
        "needs_review_n": n_rev,
        "geocode_ok": geocode_ok,
        "geocode_partial": partial,
        "error": err,
    }


def _append_history(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _print_table(rows: list[dict[str, Any]]) -> None:
    cols = [
        ("id", 28),
        ("ext_s", 7),
        ("geo_s", 7),
        ("locs", 4),
        ("res", 4),
        ("rev", 4),
        ("ex_ok", 5),
        ("geo", 5),
        ("types", 40),
    ]
    header = " ".join(f"{n:{w}}" for n, w in cols)
    log(header)
    log("-" * len(header))
    for r in rows:
        types = ",".join(r.get("types_found") or [])[: cols[-1][1]]
        line = (
            f"{r['scenario_id'][:28]:28s}"
            f" {r['extract_s']:7.2f}"
            f" {r['geocode_s']:7.2f}"
            f" {r['locations_n']:4d}"
            f" {r['resolved_n']:4d}"
            f" {r['needs_review_n']:4d}"
            f" {'Y' if r['extract_ok'] else 'N':5s}"
            f" {'Y' if r['geocode_ok'] else ('P' if r.get('geocode_partial') else 'N'):5s}"
            f" {types}"
        )
        log(line)
        if r.get("extract_note"):
            log(f"  └ extract: {r['extract_note']}")
        if r.get("error"):
            log(f"  └ error: {r['error']}")


def run_in_process(corpus_path: Path, history_path: Path) -> int:
    os.environ.setdefault("PYTHONPATH", "")
    # Ensure agate package roots are importable when run as script
    agate_src = _REPO_ROOT / "packages" / "backfield-agate" / "src"
    if str(agate_src) not in sys.path:
        sys.path.insert(0, str(agate_src))

    from agate_runtime.context import AgateEnvContext

    rows = _load_corpus(corpus_path)
    ctx = AgateEnvContext()

    geocode_params: dict[str, Any] = {
        "maxLocations": int(rows[0].get("max_locations", 25)),
        "perLocationTimeout": int(rows[0].get("per_location_timeout", 180)),
        "useCache": False,
        "evaluationModel": os.environ.get("SMOKE_GEOCODE_EVAL_MODEL", "gpt-5-nano"),
        "routerModel": os.environ.get("SMOKE_GEOCODE_ROUTER_MODEL", "gpt-5-nano"),
    }

    if not ctx.get_api_key("OPENAI_API_KEY"):
        log("ERROR: OPENAI_API_KEY is not set (required for PlaceExtract + GeocodeAgent).")
        return 2

    results: list[dict[str, Any]] = []
    ts = datetime.now(UTC).isoformat()
    for row in rows:
        rec = _run_in_process_scenario(row, ctx=ctx, geocode_params=geocode_params)
        rec["run_at"] = ts
        rec["corpus"] = str(corpus_path)
        results.append(rec)
        _append_history(history_path, rec)

    log("")
    log(f"Corpus: {corpus_path}")
    log(f"History: {history_path}")
    log("")
    _print_table(results)

    ok_all = all(r["extract_ok"] and r["geocode_ok"] for r in results)
    log("")
    if ok_all:
        log("Summary: all scenarios passed extract + geocode gates.")
        return 0
    failed = [r["scenario_id"] for r in results if not (r["extract_ok"] and r["geocode_ok"])]
    log(f"Summary: {len(failed)} scenario(s) need attention: {', '.join(failed)}")
    return 1


def run_via_agate_api() -> int:
    agate_base = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
    stylebook_base = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
    bearer = os.environ.get("SMOKE_AGATE_BEARER") or os.environ.get(
        "SERVICE_API_TOKEN", "backfield-dev"
    )
    project_slug = os.environ.get("SMOKE_PROJECT_SLUG", "general")
    poll_timeout = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
    poll_interval = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))
    graph_id_env = os.environ.get("SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID", "").strip()

    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    ensure_health(
        agate_base=agate_base,
        stylebook_base=stylebook_base,
        agate_headers=headers,
        stylebook_headers=headers,
    )
    with httpx.Client(base_url=agate_base, timeout=15.0, headers=headers) as agate:
        projects = assert_list(agate.get("/projects"), "list projects")
        project = next(
            (p for p in projects if isinstance(p, dict) and p.get("slug") == project_slug),
            None,
        )
        if project is None:
            raise RuntimeError(f"No project with slug {project_slug!r}")
        project_id = int(project["id"])

        graph_id = graph_id_env
        graph_name = "(env)"
        if not graph_id:
            graphs = assert_list(agate.get("/graphs"), "list graphs")
            from agate_runtime import STARTER_FLOW_GRAPH_DISPLAY_NAME

            starter = next(
                (
                    g
                    for g in graphs
                    if isinstance(g, dict)
                    and g.get("project_id") == project_id
                    and g.get("name") == STARTER_FLOW_GRAPH_DISPLAY_NAME
                ),
                None,
            )
            if starter is None:
                raise RuntimeError(
                    f"No graph named {STARTER_FLOW_GRAPH_DISPLAY_NAME!r} on project {project_id}. "
                    "Set SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID or bootstrap the starter flow."
                )
            graph_id = str(starter["id"])
            graph_name = str(starter.get("name", ""))

        t0 = time.perf_counter()
        run = assert_object(agate.post("/runs", json={"graph_id": graph_id}), "create run")
        terminal = wait_for_terminal_run(
            agate, str(run["id"]), timeout_s=poll_timeout, interval_s=poll_interval
        )
        elapsed = time.perf_counter() - t0

        if terminal.get("status") != "succeeded":
            raise RuntimeError(
                f"Run failed: status={terminal.get('status')} error={terminal.get('error_message')}"
            )
        result = terminal.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Run result must be an object")

        log(
            f"Stack smoke OK in {elapsed:.1f}s "
            f"(graph {graph_name!r} id={graph_id} run={terminal.get('id')})."
        )
        if graph_id_env:
            log("Used SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID.")
        else:
            log(
                "Used Starter flow graph (GeocodeAgent). "
                "To use a different graph, set SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID."
            )
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PlaceExtract + GeocodeAgent smoke harness.")
    parser.add_argument(
        "--via-agate-api",
        action="store_true",
        help="Enqueue one Agate run (see module docstring) instead of in-process corpus.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(os.environ.get("SMOKE_PLACE_GEOCODE_CORPUS", str(_DEFAULT_CORPUS))),
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path(os.environ.get("SMOKE_PLACE_GEOCODE_HISTORY", str(_DEFAULT_HISTORY))),
    )
    args = parser.parse_args(argv)

    if args.via_agate_api:
        return run_via_agate_api()
    return run_in_process(args.corpus.resolve(), args.history.resolve())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
