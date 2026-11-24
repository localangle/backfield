"""Backfill `merged_into` redirects for merges made before redirects were recorded."""

from __future__ import annotations

import argparse
import json
import logging

from backfield_db.session import get_engine
from backfield_entities.cleanup.redirect_backfill import BackfillReport, backfill_merge_redirects
from sqlmodel import Session

from backfield_cli.console import CONSOLE

logger = logging.getLogger(__name__)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "backfill-merge-redirects",
        help=(
            "Write redirects for merges made before redirects existed, from the activity log "
            "(dry-run by default)"
        ),
    )
    parser.add_argument(
        "--stylebook-id",
        type=int,
        default=None,
        help="Limit the backfill to one Stylebook id",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the redirects (default is dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )
    parser.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        with Session(get_engine()) as session:
            report = backfill_merge_redirects(
                session, stylebook_id=args.stylebook_id, dry_run=not bool(args.apply)
            )
            if args.apply:
                session.commit()
    except Exception as error:
        logger.error("Merge redirect backfill failed: %s", error)
        CONSOLE.print(f"[red]Merge redirect backfill failed: {error}[/red]")
        return 2

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0
    _print_report(report)
    return 0


def _print_report(report: BackfillReport) -> None:
    mode = "dry-run" if report.dry_run else "apply"
    written_label = "would write" if report.dry_run else "written"
    CONSOLE.print(f"[bold]Merge redirect backfill ({mode})[/bold]")
    for entity_type, counts in sorted(report.by_entity.items()):
        CONSOLE.print(
            f"  {entity_type}: {counts.merges_found} merged ids, {written_label} "
            f"{counts.written}, already present {counts.already_present}, "
            f"old record still exists {counts.old_record_still_exists}, "
            f"survivor missing {counts.survivor_missing}, cycles {counts.cycles}"
        )
    if report.survivor_missing_samples:
        CONSOLE.print(
            "  survivor missing, examples: " + json.dumps(report.survivor_missing_samples)
        )
