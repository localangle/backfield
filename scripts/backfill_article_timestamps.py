#!/usr/bin/env python3
"""One-off: backfill substrate_article.published / updated from processed-item JSON.

Not registered on the ``backfield`` CLI menu. Run from the repo root:

  uv run python scripts/backfill_article_timestamps.py
  uv run python scripts/backfill_article_timestamps.py --apply
  uv run python scripts/backfill_article_timestamps.py --project-slug general --json
  uv run python scripts/backfill_article_timestamps.py --project-id 1 --limit 100 --apply

Dry-run by default. Only fills null columns. Does not invent ``published`` from
``updated`` or ``pub_date``. Uses ``BACKFIELD_DATABASE_URL`` (then ``DATABASE_URL``).
"""

from __future__ import annotations

import argparse
import json
import sys

from backfield_db.session import get_engine
from backfield_entities.ingest.article_timestamps import backfill_article_timestamps
from sqlmodel import Session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill null article published/updated timestamps from processed-item JSON "
            "(dry-run by default; not a backfield CLI subcommand)."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit timestamp fills (default is dry-run)",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        default=None,
        help="Limit backfill to one project id",
    )
    parser.add_argument(
        "--project-slug",
        default=None,
        help="Limit backfill to one project slug (must be unique)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum articles with null published or updated to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )
    args = parser.parse_args(argv)

    try:
        with Session(get_engine()) as session:
            report = backfill_article_timestamps(
                session,
                apply=bool(args.apply),
                project_id=args.project_id,
                project_slug=args.project_slug,
                limit=args.limit,
            )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    payload = {
        "mode": "apply" if args.apply else "dry-run",
        "project_id": args.project_id,
        "project_slug": args.project_slug,
        "limit": args.limit,
        "scanned": report.scanned,
        "published_filled": report.published_filled,
        "updated_filled": report.updated_filled,
        "unchanged": report.unchanged,
        "missing_source": report.missing_source,
        "article_ids_published": report.article_ids_published,
        "article_ids_updated": report.article_ids_updated,
        "missing_source_ids": report.missing_source_ids,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    published_label = "published filled" if args.apply else "would fill published"
    updated_label = "updated filled" if args.apply else "would fill updated"
    print(f"Article timestamp backfill ({payload['mode']})")
    if args.project_id is not None:
        print(f"  project_id: {args.project_id}")
    if args.project_slug:
        print(f"  project_slug: {args.project_slug}")
    if args.limit is not None:
        print(f"  limit: {args.limit}")
    print(f"  scanned: {report.scanned}")
    print(f"  {published_label}: {report.published_filled}")
    print(f"  {updated_label}: {report.updated_filled}")
    print(f"  unchanged: {report.unchanged}")
    print(f"  missing source: {report.missing_source}")
    if report.article_ids_updated:
        shown = ", ".join(str(aid) for aid in report.article_ids_updated[:20])
        print(f"  article_ids_updated ({len(report.article_ids_updated)}): {shown}")
        if len(report.article_ids_updated) > 20:
            print(f"    … and {len(report.article_ids_updated) - 20} more")
    if report.article_ids_published:
        shown = ", ".join(str(aid) for aid in report.article_ids_published[:20])
        print(f"  article_ids_published ({len(report.article_ids_published)}): {shown}")
        if len(report.article_ids_published) > 20:
            print(f"    … and {len(report.article_ids_published) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
