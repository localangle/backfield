"""Repair substrate_article.external_source for legacy S3 ledger rows."""

from __future__ import annotations

import argparse
import json
import logging

from backfield_db.session import get_engine
from backfield_entities.ingest.article_external_identity import (
    S3ArticleSourceRepairReport,
    repair_s3_article_external_sources,
)
from sqlmodel import Session

from backfield_cli.console import CONSOLE

logger = logging.getLogger(__name__)


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "repair-s3-article-sources",
        help=(
            "Rewrite legacy backfield_s3_ingestion article sources to publication/outlet names"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit source rewrites (default is dry-run)",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        default=None,
        help="Limit repair to one project id",
    )
    parser.add_argument(
        "--project-slug",
        default=None,
        help="Limit repair to one project slug (must be unique)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the repair report as JSON",
    )
    parser.set_defaults(handler=_run)


def _report_to_dict(report: S3ArticleSourceRepairReport) -> dict[str, object]:
    return {
        "scanned": report.scanned,
        "updated": report.updated,
        "unchanged": report.unchanged,
        "collision_skipped": report.collision_skipped,
        "unresolved": report.unresolved,
        "collisions": report.collisions,
        "unresolved_ids": report.unresolved_ids,
    }


def _run(args: argparse.Namespace) -> int:
    try:
        with Session(get_engine()) as session:
            report = repair_s3_article_external_sources(
                session,
                apply=bool(args.apply),
                project_id=args.project_id,
                project_slug=args.project_slug,
            )
    except ValueError as error:
        logger.error("%s", error)
        CONSOLE.print(f"[red]{error}[/red]")
        return 1
    except Exception as error:
        logger.error("S3 article source repair failed: %s", error)
        return 2

    payload = _report_to_dict(report)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "apply" if args.apply else "dry-run"
        updated_label = "updated" if args.apply else "would update"
        CONSOLE.print(f"[bold]S3 article source repair ({mode})[/bold]")
        CONSOLE.print(f"  scanned: {report.scanned}")
        CONSOLE.print(f"  {updated_label}: {report.updated}")
        CONSOLE.print(f"  unchanged: {report.unchanged}")
        CONSOLE.print(f"  collision skipped: {report.collision_skipped}")
        CONSOLE.print(f"  unresolved: {report.unresolved}")
        if report.collisions:
            CONSOLE.print("[yellow]Collisions (left as backfield_s3_ingestion):[/yellow]")
            for row in report.collisions:
                CONSOLE.print(
                    f"  article_id={row['article_id']} external_id={row['external_id']} "
                    f"target_source={row['target_source']!r}"
                )
    return 0
