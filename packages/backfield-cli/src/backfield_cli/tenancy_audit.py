"""Read-only organization tenancy preflight command."""

from __future__ import annotations

import argparse
import logging

from backfield_db.session import get_engine
from backfield_db.tenancy_audit import audit_tenancy
from sqlmodel import Session

from backfield_cli.console import CONSOLE

logger = logging.getLogger(__name__)


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "tenancy-audit",
        help="Report project workspace and Stylebook migration blockers",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the typed audit report as JSON",
    )
    parser.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        with Session(get_engine()) as session:
            report = audit_tenancy(session)
    except Exception as error:
        logger.error("Tenancy audit failed: %s", error)
        return 2

    if args.json:
        print(report.to_json())
    elif report.ok:
        CONSOLE.print("[green]Tenancy audit passed: no blockers found.[/green]")
    else:
        CONSOLE.print(f"[red]Tenancy audit found {report.blocker_count} blocker(s):[/red]")
        for blocker in report.blockers:
            CONSOLE.print(f"  [red]{blocker.code.value}[/red] {blocker.message}")
    return 0 if report.ok else 1
