"""Backfield CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from backfield_cli import doctor as doctor_cmd
from backfield_cli import init as init_cmd
from backfield_cli import migrate as migrate_cmd
from backfield_cli import seed as seed_cmd
from backfield_cli import stack_cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backfield", description="Backfield operator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate_cmd.register_subcommand(subparsers)
    seed_cmd.register_subcommand(subparsers)
    init_cmd.register_subcommand(subparsers)
    doctor_cmd.register_subcommand(subparsers)
    stack_cmd.register_subcommands(subparsers)
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error("command required")
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
