"""Repair open connections whose endpoints no longer exist."""

from __future__ import annotations

import argparse
import json
import logging

from backfield_db.session import get_engine
from backfield_entities.connections.lifecycle import repair_orphan_open_connections
from sqlmodel import Session

from backfield_cli.console import CONSOLE

logger = logging.getLogger(__name__)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "repair-orphan-connections",
        help=(
            "Rewire or soft-close open Stylebook connections whose endpoints "
            "were deleted (dry-run by default)"
        ),
    )
    parser.add_argument(
        "--stylebook-id",
        type=int,
        default=None,
        help="Limit repair to one Stylebook id",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit rewires and soft-closes (default is dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the repair report as JSON",
    )
    parser.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    dry_run = not bool(args.apply)
    try:
        with Session(get_engine()) as session:
            result = repair_orphan_open_connections(
                session,
                stylebook_id=args.stylebook_id,
                dry_run=dry_run,
            )
            if args.apply:
                session.commit()
    except Exception as error:
        logger.error("Orphan connection repair failed: %s", error)
        CONSOLE.print(f"[red]Orphan connection repair failed: {error}[/red]")
        return 2

    payload = {
        "mode": "apply" if args.apply else "dry-run",
        "stylebook_id": args.stylebook_id,
        "inspected_count": result.inspected_count,
        "rewired_count": result.rewired_count,
        "closed_count": result.closed_count,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    CONSOLE.print(f"[bold]Orphan connection repair ({payload['mode']})[/bold]")
    if args.stylebook_id is not None:
        CONSOLE.print(f"  stylebook_id: {args.stylebook_id}")
    CONSOLE.print(f"  inspected: {result.inspected_count}")
    rewired_label = "rewired" if args.apply else "would rewire"
    closed_label = "closed" if args.apply else "would close"
    CONSOLE.print(f"  {rewired_label}: {result.rewired_count}")
    CONSOLE.print(f"  {closed_label}: {result.closed_count}")
    return 0
