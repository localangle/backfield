"""Operator subcommands for the local Docker Compose stack."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from backfield_cli.console import CONSOLE
from backfield_cli.stack import (
    ComposeContext,
    compose_command_for_context,
    resolve_compose_context,
)

logger = logging.getLogger(__name__)

CLEAR_ENTITY_DATA_SCRIPT = "packages/backfield-db/scripts/clear_entity_data.py"


def register_subcommands(subparsers) -> None:
    _register_up(subparsers)
    _register_down(subparsers)
    _register_logs(subparsers)
    _register_ps(subparsers)
    _register_restart(subparsers)
    _register_reset_db(subparsers)
    _register_clear_entity_data(subparsers)


def _add_compose_file_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--compose-file",
        default=None,
        help="Path to docker-compose.yml (overrides BACKFIELD_COMPOSE_FILE and discovery)",
    )


def _register_up(subparsers) -> None:
    parser = subparsers.add_parser("up", help="Start the local stack")
    _add_compose_file_arg(parser)
    parser.add_argument(
        "--detached",
        "-d",
        action="store_true",
        help="Run in the background (docker compose up -d)",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Do not build images before starting",
    )
    parser.set_defaults(handler=_run_up)


def _register_down(subparsers) -> None:
    parser = subparsers.add_parser("down", help="Stop the local stack")
    _add_compose_file_arg(parser)
    parser.set_defaults(handler=_run_down)


def _register_logs(subparsers) -> None:
    parser = subparsers.add_parser("logs", help="Show stack logs (follows by default)")
    _add_compose_file_arg(parser)
    parser.add_argument(
        "services",
        nargs="*",
        help="Optional service names to filter logs",
    )
    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="Print current logs and exit instead of following",
    )
    parser.set_defaults(handler=_run_logs)


def _register_ps(subparsers) -> None:
    parser = subparsers.add_parser("ps", help="List stack containers")
    _add_compose_file_arg(parser)
    parser.set_defaults(handler=_run_ps)


def _register_restart(subparsers) -> None:
    parser = subparsers.add_parser("restart", help="Restart stack services")
    _add_compose_file_arg(parser)
    parser.add_argument(
        "services",
        nargs="*",
        help="Optional service names to restart (default: all)",
    )
    parser.set_defaults(handler=_run_restart)


def _register_reset_db(subparsers) -> None:
    parser = subparsers.add_parser(
        "reset-db",
        help="Stop the stack and remove volumes (deletes all local data)",
    )
    _add_compose_file_arg(parser)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    parser.set_defaults(handler=_run_reset_db)


def _register_clear_entity_data(subparsers) -> None:
    parser = subparsers.add_parser(
        "clear-entity-data",
        help="Truncate substrate/stylebook entity and Agate run tables (local dev)",
    )
    _add_compose_file_arg(parser)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    parser.set_defaults(handler=_run_clear_entity_data)


def _resolve_context(args: argparse.Namespace) -> ComposeContext:
    return resolve_compose_context(args.compose_file)


def _run_compose(context: ComposeContext, *args: str) -> int:
    command = compose_command_for_context(context, *args)
    try:
        result = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        return 130
    return int(result.returncode)


def _run_up(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    compose_args = ["up"]
    if args.detached:
        compose_args.append("-d")
    if not args.no_build:
        compose_args.append("--build")
    return _run_compose(context, *compose_args)


def _run_down(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    return _run_compose(context, "down")


def _run_logs(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    compose_args = ["logs"]
    if not args.no_follow:
        compose_args.append("-f")
    compose_args.extend(args.services)
    return _run_compose(context, *compose_args)


def _run_ps(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    return _run_compose(context, "ps")


def _run_restart(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    return _run_compose(context, "restart", *args.services)


def _confirm(prompt: str, *, skip: bool) -> bool:
    if skip:
        return True
    if not sys.stdin.isatty():
        CONSOLE.print("[red]Refusing to run without --yes in a non-interactive session.[/red]")
        return False
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _run_reset_db(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    if not _confirm(
        "This removes all local Backfield data (Postgres volume). Continue?",
        skip=args.yes,
    ):
        CONSOLE.print("Aborted.")
        return 1
    return _run_compose(context, "down", "-v")


def _run_clear_entity_data(args: argparse.Namespace) -> int:
    context = _resolve_context(args)
    if not _confirm(
        "This truncates substrate/stylebook entity and Agate run tables. Continue?",
        skip=args.yes,
    ):
        CONSOLE.print("Aborted.")
        return 1
    script_path = context.repo_root / CLEAR_ENTITY_DATA_SCRIPT
    if not script_path.is_file():
        CONSOLE.print(f"[red]Clear-entity-data script not found: {script_path}[/red]")
        return 1
    import os

    env = dict(os.environ)
    env["BACKFIELD_CONFIRM_CLEAR"] = "1"
    try:
        result = subprocess.run([sys.executable, str(script_path)], check=False, env=env)
    except KeyboardInterrupt:
        return 130
    return int(result.returncode)
