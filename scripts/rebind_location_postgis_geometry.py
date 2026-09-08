#!/usr/bin/env python3
"""One-off: rebind PostGIS geometry from geometry_json for half-updated locations.

Not registered on the ``backfield`` CLI menu. Run from the repo root:

  uv run python scripts/rebind_location_postgis_geometry.py
  uv run python scripts/rebind_location_postgis_geometry.py --apply
  uv run python scripts/rebind_location_postgis_geometry.py --stylebook-id 1 --apply

Dry-run by default. Targets catalog and saved-place rows where ``geometry_json`` is
present and convertible but PostGIS ``geometry`` is null (the MultiPolygon title() bug
state). Article geo-search requires PostGIS.
"""

from __future__ import annotations

import argparse
import json
import sys

from backfield_db.session import get_engine
from backfield_entities.geo.rebind_postgis import rebind_missing_location_postgis_geometry
from sqlmodel import Session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebind PostGIS geometry from stored GeoJSON where geometry is null "
            "(dry-run by default; not a backfield CLI subcommand)."
        )
    )
    parser.add_argument(
        "--stylebook-id",
        type=int,
        default=None,
        help="Limit to one Stylebook catalog and its linked saved places",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        default=None,
        help="Limit saved-place scan to one project id",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum rows to inspect across catalog + saved places",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit PostGIS rebinds (default is dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )
    args = parser.parse_args(argv)

    dry_run = not bool(args.apply)
    with Session(get_engine()) as session:
        result = rebind_missing_location_postgis_geometry(
            session,
            stylebook_id=args.stylebook_id,
            project_id=args.project_id,
            dry_run=dry_run,
            limit=args.limit,
        )
        if args.apply:
            session.commit()

    payload = {
        "mode": "apply" if args.apply else "dry-run",
        "stylebook_id": args.stylebook_id,
        "project_id": args.project_id,
        "inspected_count": result.inspected_count,
        "rebound_count": result.rebound_count,
        "canonical_ids": list(result.canonical_ids),
        "substrate_ids": list(result.substrate_ids),
        "skipped": [
            {"table": item.table, "id": item.id, "reason": item.reason} for item in result.skipped
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    label = "Rebound" if args.apply else "Would rebind"
    print(f"PostGIS geometry rebind ({payload['mode']})")
    if args.stylebook_id is not None:
        print(f"  stylebook_id: {args.stylebook_id}")
    if args.project_id is not None:
        print(f"  project_id: {args.project_id}")
    print(f"  inspected: {result.inspected_count}")
    print(f"  {label.lower()}: {result.rebound_count}")
    print(f"  skipped: {len(result.skipped)}")
    if result.canonical_ids:
        print(
            f"  canonical_ids ({len(result.canonical_ids)}): {', '.join(result.canonical_ids[:20])}"
        )
        if len(result.canonical_ids) > 20:
            print(f"    … and {len(result.canonical_ids) - 20} more")
    if result.substrate_ids:
        shown = ", ".join(str(sid) for sid in result.substrate_ids[:20])
        print(f"  substrate_ids ({len(result.substrate_ids)}): {shown}")
        if len(result.substrate_ids) > 20:
            print(f"    … and {len(result.substrate_ids) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
