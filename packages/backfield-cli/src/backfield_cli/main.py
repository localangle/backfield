"""Backfield CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from backfield_cli import migrate as migrate_cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backfield", description="Backfield operator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate_cmd.register_subcommand(subparsers)
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error("command required")
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
