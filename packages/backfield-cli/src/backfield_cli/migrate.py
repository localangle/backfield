"""Migration subcommand and backfield-migrate console-script alias."""

from __future__ import annotations

import argparse

from backfield_db.migrate import main as run_migrate_main


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "migrate",
        help="Run database migrations (Alembic upgrade head)",
    )
    parser.set_defaults(handler=_run_migrate)


def _run_migrate(_args: argparse.Namespace) -> int:
    return run_migrate_main()


def main() -> int:
    return run_migrate_main()
