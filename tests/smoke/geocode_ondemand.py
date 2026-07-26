#!/usr/bin/env python3
"""On-demand multi-type geocode regression against local DB snapshots.

Not part of ``make test``. Builds a gitignored corpus of prior failures and
successes for ``place``, ``street_road``, ``natural``, and ``address`` from
``agate_processed_item``, then re-runs the matching model geocode path.

Examples::

    uv run python -u tests/smoke/geocode_ondemand.py --build
    uv run python -u tests/smoke/geocode_ondemand.py --run
    uv run python -u tests/smoke/geocode_ondemand.py --build --run
    uv run python -u tests/smoke/geocode_ondemand.py --build --run --per-bucket 8
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE_DIR = Path(__file__).resolve().parent
_DEFAULT_CORPUS = _SMOKE_DIR / "artifacts" / "geocode_ondemand_corpus.json"
_DEFAULT_RESULTS = _SMOKE_DIR / "artifacts" / "geocode_ondemand_results.jsonl"

_TARGET_TYPES = ("place", "street_road", "natural", "address")
_DEFAULT_PER_BUCKET = 10
_MIN_ITEM_ID = 600


def _log(msg: str) -> None:
    print(msg, flush=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "loc"


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


def _state_abbr(components: dict[str, Any]) -> str | None:
    state_info = components.get("state")
    if isinstance(state_info, dict):
        return str(state_info.get("abbr") or "").strip() or None
    if isinstance(state_info, str):
        return state_info.strip() or None
    return None


def _state_name(components: dict[str, Any]) -> str | None:
    state_info = components.get("state")
    if isinstance(state_info, dict):
        return str(state_info.get("name") or "").strip() or None
    return None


def _parse_location_jurisdiction(
    location: str,
    *,
    city: str | None,
    state_abbr: str | None,
    country: str,
) -> tuple[str | None, str | None, str | None, str]:
    """Fill city/state/country from a comma-separated location label."""
    from agate_nodes.place_extract.location_utils import US_STATE_ABBR_BY_NAME, US_STATES

    parts = [part.strip() for part in location.split(",") if part.strip()]
    state_name: str | None = None
    if not parts:
        return city, state_abbr, state_name, country

    tail = parts[-1]
    tail_upper = tail.upper()
    if tail_upper in {"US", "USA", "UNITED STATES"}:
        country = country or "US"
        parts = parts[:-1]
    elif tail_upper in US_STATES:
        # Prefer the label's state over a stale extract abbr.
        state_abbr = tail_upper
        state_name = US_STATES[tail_upper]
        parts = parts[:-1]
    elif tail.lower() in US_STATE_ABBR_BY_NAME:
        state_abbr = US_STATE_ABBR_BY_NAME[tail.lower()]
        state_name = tail
        parts = parts[:-1]

    if not city and len(parts) >= 2:
        city = parts[-1]
    return city, state_abbr, state_name, country


def _country_code(components: dict[str, Any], *, default: str = "US") -> str:
    country_info = components.get("country")
    if isinstance(country_info, dict):
        abbr = str(country_info.get("abbr") or "").strip().upper()
        if abbr:
            return abbr
    return default


def _iter_place_entries(places: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for entry in places.get("needs_review") or []:
        if isinstance(entry, dict):
            out.append(("prior_fail", entry))
    for entry in places.get("points") or []:
        if isinstance(entry, dict):
            out.append(("prior_success", entry))
    areas = places.get("areas") if isinstance(places.get("areas"), dict) else {}
    for bucket_entries in areas.values():
        if not isinstance(bucket_entries, list):
            continue
        for entry in bucket_entries:
            if isinstance(entry, dict):
                out.append(("prior_success", entry))
    return out


def _case_from_entry(
    *,
    item_id: int,
    entry: dict[str, Any],
    prior_bucket: str,
    extract_by_full: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    location = str(entry.get("location") or "").strip()
    loc_type = str(entry.get("type") or "").strip().lower()
    if not location or loc_type not in _TARGET_TYPES:
        return None

    components = entry.get("components")
    extract = extract_by_full.get(location.lower())
    if not isinstance(components, dict) and extract:
        loc_info = extract.get("location") if isinstance(extract.get("location"), dict) else {}
        components = loc_info.get("components") if isinstance(loc_info, dict) else None
    if not isinstance(components, dict):
        components = {}

    place_info = components.get("place") if isinstance(components.get("place"), dict) else {}
    street_info = (
        components.get("street_road") if isinstance(components.get("street_road"), dict) else {}
    )
    if loc_type == "street_road":
        name = str(street_info.get("name") or location.split(",")[0]).strip()
    elif loc_type == "address":
        name = str(components.get("address") or location.split(",")[0]).strip()
    elif loc_type == "natural":
        name = str(place_info.get("name") or location.split(",")[0]).strip()
    else:
        name = str(place_info.get("name") or location.split(",")[0]).strip()

    city = str(components.get("city") or "").strip() or None
    state_abbr = _state_abbr(components)
    state_name = _state_name(components)
    country = _country_code(components, default="US" if loc_type != "natural" else "")
    street = str(components.get("address") or "").strip() or None

    city, state_abbr, parsed_state_name, country = _parse_location_jurisdiction(
        location, city=city, state_abbr=state_abbr, country=country or ""
    )
    state_name = state_name or parsed_state_name
    if state_abbr in {"US", "USA"}:
        country = country or "US"
        state_abbr = None

    geo = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else {}
    result = geo.get("result") if isinstance(geo.get("result"), dict) else {}
    audit = (
        entry.get("agate_geocode_router_audit")
        if isinstance(entry.get("agate_geocode_router_audit"), dict)
        else {}
    )
    return {
        "id": f"{loc_type}:{prior_bucket}:{item_id}:{_slug(name)}",
        "item_id": item_id,
        "prior_bucket": prior_bucket,
        "location": location,
        "type": loc_type,
        "name": name,
        "city": city,
        "state_abbr": state_abbr,
        "state_name": state_name,
        "country": country or None,
        "street_address": street,
        "components": components,
        "original_text": entry.get("original_text")
        or (extract or {}).get("original_text")
        or "",
        "geocode_hints": entry.get("geocode_hints")
        or (extract or {}).get("geocode_hints")
        or "",
        "description": entry.get("description") or (extract or {}).get("description") or "",
        "prior_reason": entry.get("reason") or entry.get("geocode_qa_code"),
        "prior_strategy": audit.get("strategy_selected"),
        "prior_formatted": result.get("formatted_address") or result.get("processed_str"),
        "place_is_natural": bool(place_info.get("natural")) if place_info else False,
    }


def _sample_cases(
    candidates: list[dict[str, Any]],
    *,
    per_bucket: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case in candidates:
        key = (str(case["type"]), str(case["prior_bucket"]))
        by_key.setdefault(key, []).append(case)

    rng = random.Random(seed) if seed is not None else None
    ordered: list[dict[str, Any]] = []
    for loc_type in _TARGET_TYPES:
        for bucket in ("prior_fail", "prior_success"):
            rows = list(by_key.get((loc_type, bucket), []))
            if rng is not None:
                rng.shuffle(rows)
            else:
                rows.sort(key=lambda c: (int(c["item_id"]), str(c["location"]).lower()))
            ordered.extend(rows[:per_bucket])
    return ordered


def build_corpus(
    corpus_path: Path,
    *,
    per_bucket: int,
    min_item_id: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    csv.field_size_limit(10**9)
    raw = _psql(
        "COPY ("
        "SELECT id, replace(result_json, E'\\\\u0000', '') "
        f"FROM agate_processed_item WHERE id >= {int(min_item_id)} "
        "AND result_json LIKE '%geocode_agent%' "
        "ORDER BY id"
        ") TO STDOUT WITH (FORMAT csv);"
    )
    candidates: list[dict[str, Any]] = []
    for rec in csv.reader(raw.splitlines()):
        if len(rec) != 2:
            continue
        try:
            item_id = int(rec[0])
            data = json.loads(rec[1])
        except Exception:
            continue
        places = (data.get("geocode_agent") or {}).get("places") or {}
        extract_by_full: dict[str, dict[str, Any]] = {}
        for loc in (data.get("place_extract") or {}).get("locations") or []:
            if not isinstance(loc, dict):
                continue
            loc_info = loc.get("location") if isinstance(loc.get("location"), dict) else {}
            full = str(loc_info.get("full") or "").strip()
            if full:
                extract_by_full[full.lower()] = loc
        for bucket, entry in _iter_place_entries(places):
            case = _case_from_entry(
                item_id=item_id,
                entry=entry,
                prior_bucket=bucket,
                extract_by_full=extract_by_full,
            )
            if case is not None:
                candidates.append(case)

    ordered = _sample_cases(candidates, per_bucket=per_bucket, seed=seed)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": datetime.now(UTC).isoformat(),
        "case_count": len(ordered),
        "per_bucket": per_bucket,
        "min_item_id": min_item_id,
        "seed": seed,
        "types": list(_TARGET_TYPES),
        "cases": ordered,
    }
    corpus_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for case in ordered:
        key = f"{case['type']}/{case['prior_bucket']}"
        counts[key] = counts.get(key, 0) + 1
    _log(f"Wrote {len(ordered)} cases to {corpus_path}")
    for key in sorted(counts):
        _log(f"  {key}: {counts[key]}")
    return ordered


def _load_cases(corpus_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise RuntimeError(f"No cases in corpus: {corpus_path}")
    return [case for case in cases if isinstance(case, dict)]


def _bbox_extent(result: Any) -> dict[str, float] | None:
    try:
        geom = result.result.geometry
        if getattr(geom, "type", None) != "Polygon":
            return None
        ring = geom.coordinates[0]
        lons = [float(pt[0]) for pt in ring]
        lats = [float(pt[1]) for pt in ring]
        west, east = min(lons), max(lons)
        south, north = min(lats), max(lats)
        return {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "width_deg": round(east - west, 6),
            "height_deg": round(north - south, 6),
        }
    except Exception:
        return None


def _build_model(case: dict[str, Any]) -> Any:
    loc_type = str(case.get("type") or "")
    components = case.get("components") if isinstance(case.get("components"), dict) else {}
    name = str(case.get("name") or case.get("location") or "")
    city = case.get("city") or None
    state_abbr = case.get("state_abbr") or None
    country = str(case.get("country") or ("US" if loc_type != "natural" else ""))
    original_text = str(case.get("original_text") or "")
    hints = str(case.get("geocode_hints") or "").strip() or None

    if loc_type == "place":
        from agate_nodes.geocode_agent.models.point.place import Place

        model = Place(
            name=name,
            city=city,
            state_abbr=state_abbr,
            country=country or "US",
            street_address=case.get("street_address") or None,
        )
        model._input_addressability = True
        model._original_text = original_text
        model._geocode_hints = hints
        return model

    if loc_type == "address":
        from agate_nodes.geocode_agent.models.point.address import Address

        model = Address(
            name=name,
            city=city,
            state_abbr=state_abbr,
            country=country or "US",
        )
        model._original_text = original_text
        model._geocode_hints = hints
        return model

    if loc_type == "street_road":
        from agate_nodes.geocode_agent.models.area.street_road import StreetRoad

        model = StreetRoad(
            name=name,
            city=city or "",
            state=state_abbr or "",
            country=country or "US",
        )
        model._geocode_hints = hints
        return model

    if loc_type == "natural":
        from agate_nodes.geocode_agent.models.area.natural import NaturalPlace

        place_info = components.get("place") if isinstance(components.get("place"), dict) else {}
        natural_kwargs: dict[str, Any] = {
            "name": name,
            "city": city,
            "state": case.get("state_name") or None,
            "state_abbr": state_abbr if state_abbr not in {"US", "USA"} else None,
            "place_name": str(place_info.get("name") or name),
            "place_is_natural": bool(case.get("place_is_natural") or place_info.get("natural")),
            "additional_context": (
                f"Original text: {original_text}\nGeocode hints: {hints}"
                if original_text or hints
                else None
            ),
        }
        if country or state_abbr in {"US", "USA"}:
            natural_kwargs["country"] = country or "US"
        return NaturalPlace(**natural_kwargs)

    raise ValueError(f"Unsupported type: {loc_type}")


async def _geocode_case(case: dict[str, Any], *, keys: dict[str, str | None]) -> dict[str, Any]:
    model = _build_model(case)
    loc_type = str(case.get("type") or "")
    t0 = time.perf_counter()
    err: str | None = None
    result = None
    try:
        if loc_type == "place":
            result = await model.geocode(
                pelias_api_key=keys.get("PELIAS_API_KEY"),
                geocodio_api_key=keys.get("GEOCODIO_API_KEY"),
                openai_api_key=keys.get("OPENAI_API_KEY"),
                brave_search_api_key=keys.get("BRAVE_SEARCH_API_KEY"),
                allow_web_search=True,
            )
        elif loc_type == "street_road":
            result = await model.geocode(
                pelias_api_key=keys.get("PELIAS_API_KEY"),
                geocodio_api_key=keys.get("GEOCODIO_API_KEY"),
                openai_api_key=keys.get("OPENAI_API_KEY"),
                original_text=str(case.get("original_text") or ""),
            )
        else:
            result = await model.geocode(
                pelias_api_key=keys.get("PELIAS_API_KEY"),
                geocodio_api_key=keys.get("GEOCODIO_API_KEY"),
                openai_api_key=keys.get("OPENAI_API_KEY"),
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
    geocoder = None
    bbox = None
    if result is not None:
        try:
            processed = result.result.processed_str
            geocoder = result.geocoder
            bbox = _bbox_extent(result)
        except Exception:
            processed = None

    return {
        "id": case.get("id"),
        "item_id": case.get("item_id"),
        "type": loc_type,
        "location": case.get("location"),
        "prior_bucket": prior,
        "prior_formatted": case.get("prior_formatted"),
        "resolved": resolved,
        "outcome": outcome,
        "formatted": processed,
        "geocoder": geocoder,
        "bbox_extent": bbox,
        "address_source": getattr(model, "_address_source", None),
        "search_attempts": list(getattr(model, "_address_search_attempts", []) or []),
        "elapsed_s": elapsed,
        "error": err,
    }


def _print_summary(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    by_type: dict[str, dict[str, int]] = {}
    for row in rows:
        key = str(row.get("outcome") or "unknown")
        counts[key] = counts.get(key, 0) + 1
        loc_type = str(row.get("type") or "?")
        by_type.setdefault(loc_type, {})
        by_type[loc_type][key] = by_type[loc_type].get(key, 0) + 1

    _log("")
    _log("Summary")
    _log("-" * 72)
    for key in ("improved", "still_fail", "still_ok", "regressed", "resolved", "failed"):
        if key in counts:
            _log(f"  {key:12s} {counts[key]:3d}")
    _log("")
    _log("By type")
    for loc_type in _TARGET_TYPES:
        if loc_type not in by_type:
            continue
        parts = ", ".join(f"{k}={v}" for k, v in sorted(by_type[loc_type].items()))
        _log(f"  {loc_type:12s} {parts}")
    _log("")
    _log(f"{'id':48s} {'type':12s} {'out':10s} {'geo':18s} {'s':6s} location")
    _log("-" * 120)
    for row in rows:
        bbox = row.get("bbox_extent") if isinstance(row.get("bbox_extent"), dict) else None
        bbox_note = ""
        if bbox:
            bbox_note = f" bbox={bbox.get('width_deg')}x{bbox.get('height_deg')}"
        _log(
            f"{str(row.get('id') or '')[:48]:48s} "
            f"{str(row.get('type') or '')[:12]:12s} "
            f"{str(row.get('outcome') or '')[:10]:10s} "
            f"{str(row.get('geocoder') or row.get('address_source') or '-')[:18]:18s} "
            f"{float(row.get('elapsed_s') or 0):6.1f} "
            f"{row.get('location')}{bbox_note}"
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
        _log("WARNING: BRAVE_SEARCH_API_KEY missing; place waterfall will skip Brave stages")

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
    parser.add_argument(
        "--per-bucket",
        type=int,
        default=_DEFAULT_PER_BUCKET,
        help="Max prior_fail and prior_success cases per type",
    )
    parser.add_argument(
        "--min-item-id",
        type=int,
        default=_MIN_ITEM_ID,
        help="Only sample processed items at or above this id",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional case cap for debugging")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="If set, randomly sample within each type/bucket using this seed",
    )
    args = parser.parse_args()

    do_build = args.build or not args.corpus.exists()
    do_run = args.run or not args.build
    if args.build and not args.run:
        do_run = False
    if not args.build and args.run:
        do_build = not args.corpus.exists()

    if do_build:
        build_corpus(
            args.corpus.resolve(),
            per_bucket=args.per_bucket,
            min_item_id=args.min_item_id,
            seed=args.seed,
        )
    if do_run:
        return asyncio.run(
            run_corpus(args.corpus.resolve(), args.results.resolve(), limit=args.limit)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
