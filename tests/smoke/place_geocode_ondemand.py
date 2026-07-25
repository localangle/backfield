#!/usr/bin/env python3
"""On-demand Place geocode regression against local DB snapshots.

Not part of ``make test``. Builds a gitignored corpus of prior place failures and
successes from ``agate_processed_item``, then re-runs ``Place.geocode`` with the
current Brave Web → Place → DuckDuckGo waterfall.

Examples::

    uv run python -u tests/smoke/place_geocode_ondemand.py --build
    uv run python -u tests/smoke/place_geocode_ondemand.py --run
    uv run python -u tests/smoke/place_geocode_ondemand.py --build --run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE_DIR = Path(__file__).resolve().parent
_DEFAULT_CORPUS = _SMOKE_DIR / "artifacts" / "place_geocode_ondemand_corpus.json"
_DEFAULT_RESULTS = _SMOKE_DIR / "artifacts" / "place_geocode_ondemand_results.jsonl"

# Curated local selection: prior place Needs-review + web_search successes.
_SELECTION: list[tuple[int, str, str]] = [
    # (item_id, location, prior_bucket)
    (775, "Oakland Station, Oakland, CA", "prior_fail"),
    (774, "Sunset Dunes, San Francisco, CA", "prior_fail"),
    (767, "Vine Street Recreation Fields, Lincoln, NE", "prior_fail"),
    (757, "Katy Trail State Park, MO", "prior_fail"),
    (748, "Hartsburg Ball Park, Hartsburg, MO", "prior_fail"),
    (722, "Boone Tavern, Columbia, MO", "prior_fail"),
    (714, "University of Missouri School of Journalism, Columbia, MO", "prior_fail"),
    (696, "Ammo Alley Sporting Center, Hartsburg, MO", "prior_fail"),
    (674, "Our Lady Help of Christians Catholic Church, Frankenstein, MO", "prior_fail"),
    (658, "Black School of Business at Penn State Behrend, Erie, PA", "prior_fail"),
    (636, "Ashland City Park, Ashland, MO", "prior_fail"),
    (594, "Ashland City Park, Ashland, WI", "prior_fail"),
    (758, "Welcome Home, Columbia, MO", "prior_fail"),
    (755, "Hartsburg Caboose and Cottage, Hartsburg, MO", "prior_fail"),
    (755, "Katy Trail, Hartsburg, MO", "prior_fail"),
    (739, "Camp Rising Sun, Kaiser, MO", "prior_fail"),
    (737, "Hartsburg Caboose, Hartsburg, MO", "prior_fail"),
    (737, "BlackDog Outdoors, Ashland, MO", "prior_fail"),
    (737, "Lloyd's Family Farm, Ashland, MO", "prior_fail"),
    (727, "Cooper's Landing, MO", "prior_fail"),
    (722, "Hoss's Market, Columbia, MO", "prior_fail"),
    (722, "Room 38, Columbia, MO", "prior_fail"),
    (773, "Washington Park, Chicago, IL", "prior_success"),
    (769, "Washington Park Field House, Chicago, IL", "prior_success"),
    (754, "Keene Street Medical Center, Columbia, MO", "prior_success"),
    (751, "Community United Methodist Church, Columbia, MO", "prior_success"),
    (745, "Parker-Millard Funeral Home, Columbia, MO", "prior_success"),
    (
        743,
        "Memorial Funeral Home, Crematory and Memorial Park Cemetery, Columbia, MO",
        "prior_success",
    ),
    (738, "Texas A&M University, College Station, TX", "prior_success"),
    (733, "John Warner Middle School, Columbia, MO", "prior_success"),
    (731, "Albert-Oakland Park, Columbia, MO", "prior_success"),
    (723, "La Plata High School, La Plata, MO", "prior_success"),
    (723, "Mark Twain High School, Center, MO", "prior_success"),
    (714, "Jefferson City Correctional Center, Jefferson City, MO", "prior_success"),
    (698, "North Village Park, Columbia, MO", "prior_success"),
    (697, "Kansas City Union Station, Kansas City, MO", "prior_success"),
    (697, "St. Louis Union Station, St. Louis, MO", "prior_success"),
    (696, "Rock Bridge High School, Columbia, MO", "prior_success"),
    (693, "Hickman High School, Columbia, MO", "prior_success"),
    (693, "Grant Elementary School, Columbia, MO", "prior_success"),
    (693, "Columbia Public Schools, Columbia, MO", "prior_success"),
    (684, "Columbia Independent School, Columbia, MO", "prior_success"),
    (683, "Boone County Government Center, Columbia, MO", "prior_success"),
    (683, "Douglass High School, Columbia, MO", "prior_success"),
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "place"


def _psql(sql: str) -> str:
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "postgres")}
    return subprocess.check_output(
        [
            "psql",
            "-h",
            os.environ.get("PGHOST", "127.0.0.1"),
            "-p",
            os.environ.get("PGPORT", "5433"),
            "-U",
            os.environ.get("PGUSER", "postgres"),
            "-d",
            os.environ.get("PGDATABASE", "backfield"),
            "-tAc",
            sql,
        ],
        env=env,
        text=True,
    )


def _case_from_entry(
    *,
    item_id: int,
    entry: dict[str, Any],
    prior_bucket: str,
    extract_by_full: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    location = str(entry.get("location") or "").strip()
    if not location:
        return None
    components = entry.get("components")
    extract = extract_by_full.get(location.lower())
    if not isinstance(components, dict) and extract:
        loc_info = extract.get("location") if isinstance(extract.get("location"), dict) else {}
        components = loc_info.get("components") if isinstance(loc_info, dict) else None
    if not isinstance(components, dict):
        components = {}

    place_info = components.get("place") if isinstance(components.get("place"), dict) else {}
    place_name = str(place_info.get("name") or location.split(",")[0]).strip()
    city = str(components.get("city") or "").strip() or None
    state_info = components.get("state") if isinstance(components.get("state"), dict) else {}
    state_abbr = str(state_info.get("abbr") or "").strip() or None
    country_info = components.get("country") if isinstance(components.get("country"), dict) else {}
    country = str(country_info.get("abbr") or "US").strip() or "US"
    street = str(components.get("address") or "").strip() or None

    if not city or not state_abbr:
        parts = [part.strip() for part in location.split(",") if part.strip()]
        if len(parts) >= 3:
            city = city or parts[-2]
            state_abbr = state_abbr or parts[-1]
        elif len(parts) == 2:
            maybe = parts[-1]
            if len(maybe) <= 2:
                state_abbr = state_abbr or maybe
            else:
                city = city or maybe

    geo = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else {}
    result = geo.get("result") if isinstance(geo.get("result"), dict) else {}
    audit = (
        entry.get("agate_geocode_router_audit")
        if isinstance(entry.get("agate_geocode_router_audit"), dict)
        else {}
    )
    return {
        "id": f"{prior_bucket}:{item_id}:{_slug(place_name)}",
        "item_id": item_id,
        "prior_bucket": prior_bucket,
        "location": location,
        "type": "place",
        "place_name": place_name,
        "city": city,
        "state_abbr": state_abbr,
        "country": country,
        "street_address": street,
        "components": components,
        "original_text": entry.get("original_text")
        or (extract or {}).get("original_text")
        or "",
        "geocode_hints": entry.get("geocode_hints")
        or (extract or {}).get("geocode_hints")
        or "",
        "description": entry.get("description") or (extract or {}).get("description") or "",
        "prior_reason": entry.get("reason"),
        "prior_strategy": audit.get("strategy_selected"),
        "prior_formatted": result.get("formatted_address") or result.get("processed_str"),
    }


def build_corpus(corpus_path: Path) -> list[dict[str, Any]]:
    wanted = {(item_id, location.lower()): bucket for item_id, location, bucket in _SELECTION}
    item_ids = sorted({item_id for item_id, _, _ in _SELECTION})
    found: dict[tuple[int, str], dict[str, Any]] = {}

    for item_id in item_ids:
        data = json.loads(_psql(f"SELECT result_json FROM agate_processed_item WHERE id={item_id};"))
        places = (data.get("geocode_agent") or {}).get("places") or {}
        extract_by_full: dict[str, dict[str, Any]] = {}
        for loc in (data.get("place_extract") or {}).get("locations") or []:
            if not isinstance(loc, dict):
                continue
            loc_info = loc.get("location") if isinstance(loc.get("location"), dict) else {}
            full = str(loc_info.get("full") or "").strip()
            if full:
                extract_by_full[full.lower()] = loc

        for entry in (places.get("needs_review") or []) + (places.get("points") or []):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("type") or "").lower() != "place":
                continue
            location = str(entry.get("location") or "").strip()
            key = (item_id, location.lower())
            bucket = wanted.get(key)
            if not bucket:
                continue
            case = _case_from_entry(
                item_id=item_id,
                entry=entry,
                prior_bucket=bucket,
                extract_by_full=extract_by_full,
            )
            if case is not None:
                found[key] = case

    ordered: list[dict[str, Any]] = []
    missing: list[str] = []
    for item_id, location, bucket in _SELECTION:
        case = found.get((item_id, location.lower()))
        if case is None:
            missing.append(f"{item_id}:{location}")
            continue
        ordered.append(case)

    if missing:
        raise RuntimeError(f"Missing selection rows in DB: {missing[:8]}")

    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": datetime.now(UTC).isoformat(),
        "case_count": len(ordered),
        "cases": ordered,
    }
    corpus_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _log(f"Wrote {len(ordered)} cases to {corpus_path}")
    return ordered


def _load_cases(corpus_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise RuntimeError(f"No cases in corpus: {corpus_path}")
    return [case for case in cases if isinstance(case, dict)]


async def _geocode_case(case: dict[str, Any], *, keys: dict[str, str | None]) -> dict[str, Any]:
    from agate_nodes.geocode_agent.models.point.place import Place

    place = Place(
        name=str(case["place_name"]),
        city=case.get("city") or None,
        state_abbr=case.get("state_abbr") or None,
        country=str(case.get("country") or "US"),
        street_address=case.get("street_address") or None,
    )
    place._input_addressability = True
    place._original_text = str(case.get("original_text") or "")
    hints = str(case.get("geocode_hints") or "").strip()
    place._geocode_hints = hints or None

    t0 = time.perf_counter()
    err: str | None = None
    result = None
    try:
        result = await place.geocode(
            pelias_api_key=keys.get("PELIAS_API_KEY"),
            geocodio_api_key=keys.get("GEOCODIO_API_KEY"),
            openai_api_key=keys.get("OPENAI_API_KEY"),
            brave_search_api_key=keys.get("BRAVE_SEARCH_API_KEY"),
            allow_web_search=True,
        )
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    elapsed = round(time.perf_counter() - t0, 3)

    resolved = result is not None
    prior = str(case.get("prior_bucket") or "")
    if prior == "prior_fail":
        outcome = "improved" if resolved else "still_fail"
    elif prior == "prior_success":
        outcome = "still_ok" if resolved else "regressed"
    else:
        outcome = "resolved" if resolved else "failed"

    processed = None
    if result is not None:
        try:
            processed = result.result.processed_str
        except Exception:
            processed = None

    return {
        "id": case.get("id"),
        "item_id": case.get("item_id"),
        "location": case.get("location"),
        "prior_bucket": prior,
        "prior_formatted": case.get("prior_formatted"),
        "resolved": resolved,
        "outcome": outcome,
        "formatted": processed,
        "address_source": getattr(place, "_address_source", None),
        "search_attempts": list(getattr(place, "_address_search_attempts", []) or []),
        "elapsed_s": elapsed,
        "error": err,
    }


def _print_summary(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("outcome") or "unknown")
        counts[key] = counts.get(key, 0) + 1

    _log("")
    _log("Summary")
    _log("-" * 72)
    for key in ("improved", "still_fail", "still_ok", "regressed", "resolved", "failed"):
        if key in counts:
            _log(f"  {key:12s} {counts[key]:3d}")
    _log("")
    _log(f"{'id':42s} {'prior':13s} {'out':10s} {'src':12s} {'s':6s} location")
    _log("-" * 110)
    for row in rows:
        _log(
            f"{str(row.get('id') or '')[:42]:42s} "
            f"{str(row.get('prior_bucket') or '')[:13]:13s} "
            f"{str(row.get('outcome') or '')[:10]:10s} "
            f"{str(row.get('address_source') or '-')[:12]:12s} "
            f"{float(row.get('elapsed_s') or 0):6.1f} "
            f"{row.get('location')}"
        )
        if row.get("formatted"):
            _log(f"  └ resolved: {row['formatted']}")
        if row.get("error"):
            _log(f"  └ error: {row['error']}")


async def run_corpus(corpus_path: Path, results_path: Path, *, limit: int | None) -> int:
    agate_src = _REPO_ROOT / "packages" / "backfield-agate" / "src"
    if str(agate_src) not in sys.path:
        sys.path.insert(0, str(agate_src))

    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
    keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "PELIAS_API_KEY": os.getenv("PELIAS_API_KEY"),
        "BRAVE_SEARCH_API_KEY": os.getenv("BRAVE_SEARCH_API_KEY"),
        "GEOCODIO_API_KEY": os.getenv("GEOCODIO_API_KEY"),
    }
    if not keys["OPENAI_API_KEY"]:
        _log("ERROR: OPENAI_API_KEY is required")
        return 2
    if not keys["PELIAS_API_KEY"]:
        _log("ERROR: PELIAS_API_KEY is required")
        return 2
    if not keys["BRAVE_SEARCH_API_KEY"]:
        _log("WARNING: BRAVE_SEARCH_API_KEY missing; waterfall will skip Brave stages")

    cases = _load_cases(corpus_path)
    if limit is not None:
        cases = cases[: max(0, limit)]
    _log(f"Running {len(cases)} cases from {corpus_path}")

    results_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    run_at = datetime.now(UTC).isoformat()
    with results_path.open("w", encoding="utf-8") as fh:
        for idx, case in enumerate(cases, start=1):
            _log(f"[{idx}/{len(cases)}] {case.get('id')} :: {case.get('location')}")
            row = await _geocode_case(case, keys=keys)
            row["run_at"] = run_at
            rows.append(row)
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()

    _print_summary(rows)
    _log(f"Wrote results to {results_path}")

    regressions = sum(1 for row in rows if row.get("outcome") == "regressed")
    return 1 if regressions else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Rebuild corpus from local Postgres")
    parser.add_argument("--run", action="store_true", help="Geocode each corpus case")
    parser.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    parser.add_argument("--results", type=Path, default=_DEFAULT_RESULTS)
    parser.add_argument("--limit", type=int, default=None, help="Optional case cap for debugging")
    args = parser.parse_args()

    do_build = args.build or not args.corpus.exists()
    do_run = args.run or not args.build
    if args.build and not args.run:
        do_run = False
    if not args.build and args.run:
        do_build = not args.corpus.exists()

    if do_build:
        build_corpus(args.corpus.resolve())
    if do_run:
        return asyncio.run(
            run_corpus(args.corpus.resolve(), args.results.resolve(), limit=args.limit)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
