"""Local first-run orchestration for Backfield."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import subprocess
import webbrowser
from contextlib import nullcontext
from pathlib import Path

from rich.logging import RichHandler
from rich.status import Status

from backfield_cli.console import (
    CONSOLE,
    INIT_STEP_COUNT,
    MODELS_URL,
    is_interactive,
    print_banner,
    print_intro,
    print_next_steps,
    print_step,
)
from backfield_cli.credentials import resolve_admin_password
from backfield_cli.env_file import ensure_repo_env_file, find_repo_root, load_env_into_process
from backfield_cli.host_tooling import ensure_host_python_tooling
from backfield_cli.init_config import InitConfig, load_init_config
from backfield_cli.stack import (
    bring_up_stack,
    configure_host_database_env,
    run_compose_migrate,
    wait_for_api_readiness,
)

logger = logging.getLogger(__name__)

_NO_BROWSER_ENV_VALUES = frozenset({"1", "true", "yes"})

DEFAULT_SUPERUSER_EMAIL = "admin@backfield.news"
DEFAULT_SUPERUSER_PASSWORD = "admin"
DEFAULT_SUPERUSER_USERNAME = "Admin"


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "init",
        help="Local first-run setup: env secrets, stack, migrate, seed, readiness wait",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="JSON config file for non-interactive init",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (requires --config)",
    )
    parser.add_argument(
        "--skip-stack",
        action="store_true",
        help="Skip docker compose up (stack already running)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open Settings → AI models in a browser after setup",
    )
    parser.set_defaults(handler=_run_init)


def _configure_logging(*, use_rich: bool) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    if use_rich:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            handlers=[RichHandler(console=CONSOLE, show_path=False, markup=False)],
        )
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _browser_disabled_by_env() -> bool:
    return os.environ.get("BACKFIELD_NO_BROWSER", "").strip().lower() in _NO_BROWSER_ENV_VALUES


def _resolve_open_browser(config: InitConfig, *, no_browser_flag: bool) -> bool:
    if no_browser_flag or _browser_disabled_by_env():
        return False
    return config.open_browser


def _maybe_open_browser(url: str, *, enabled: bool) -> None:
    if not enabled:
        return
    try:
        webbrowser.open(url)
    except Exception as exc:
        logger.debug("Could not open browser for %s: %s", url, exc)


def _prompt(text: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{text}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("A value is required.")


def _prompt_password(text: str, *, default: str | None = None) -> str:
    suffix = f" (default: {default})" if default else ""
    while True:
        value = getpass.getpass(f"{text}{suffix}: ")
        if value:
            return value
        if default is not None:
            return default
        print("A value is required.")


def _load_config(args: argparse.Namespace) -> InitConfig:
    if args.non_interactive:
        if not args.config:
            raise ValueError("--non-interactive requires --config")
        return load_init_config(Path(args.config))
    if args.config:
        return load_init_config(Path(args.config))

    admin_email = _prompt(
        "Superuser email (you will use this to log in)",
        default=DEFAULT_SUPERUSER_EMAIL,
    )
    admin_password = _prompt_password(
        "Superuser password",
        default=DEFAULT_SUPERUSER_PASSWORD,
    )
    admin_display_name = _prompt("Superuser username", default=DEFAULT_SUPERUSER_USERNAME)
    from backfield_db.seed import DEFAULT_ORG_NAME, DEFAULT_STYLEBOOK_NAME

    org_name = _prompt("Organization name", default=DEFAULT_ORG_NAME)
    stylebook_name = _prompt("Default Stylebook name", default=DEFAULT_STYLEBOOK_NAME)
    return InitConfig(
        admin_email=admin_email,
        admin_password=admin_password,
        admin_display_name=admin_display_name,
        org_name=org_name,
        stylebook_name=stylebook_name,
        skip_stack=args.skip_stack,
    )


def run_init(config: InitConfig, *, repo_root: Path, interactive: bool = False) -> int:
    ensure_host_python_tooling(repo_root, quiet=True)

    if interactive:
        CONSOLE.print()

    if interactive:
        print_step(1, INIT_STEP_COUNT, "Prepare environment secrets")
    env_report = ensure_repo_env_file(repo_root)
    if env_report.created_env_file:
        logger.info("Created %s", env_report.env_path)
    if env_report.generated_keys:
        logger.info("Generated env keys: %s", ", ".join(env_report.generated_keys))
    else:
        logger.info("Existing env secrets left unchanged")

    load_env_into_process(env_report.env_path)

    if not config.skip_stack:
        if interactive:
            print_step(2, INIT_STEP_COUNT, "Start Docker Compose stack")
        bring_up_stack(repo_root)
    else:
        if interactive:
            print_step(2, INIT_STEP_COUNT, "Start Docker Compose stack (skipped)")
        logger.info("Skipping docker compose up (--skip-stack)")

    if interactive:
        print_step(3, INIT_STEP_COUNT, "Run database migrations")
    run_compose_migrate(repo_root)

    if interactive:
        print_step(4, INIT_STEP_COUNT, "Wait for API readiness")
    readiness_context: Status | nullcontext
    if interactive:
        readiness_context = CONSOLE.status("[bold cyan]Waiting for APIs to become ready...[/]")
    else:
        readiness_context = nullcontext()
    with readiness_context:
        wait_for_api_readiness(repo_root)

    if interactive:
        print_step(5, INIT_STEP_COUNT, "Seed organization and admin user")
    configure_host_database_env()
    admin_password = resolve_admin_password(
        password=config.admin_password,
        password_file=config.admin_password_file,
    )
    from backfield_db.seed import run_init_seed

    report = run_init_seed(
        org_name=config.org_name,
        stylebook_name=config.stylebook_name,
        admin_email=config.admin_email,
        admin_password=admin_password,
        admin_display_name=config.admin_display_name,
    )
    logger.info(
        "Init seed complete organization_id=%s organization_created=%s admin_created=%s "
        "admin_email=%s",
        report.organization_id,
        report.organization_created,
        report.admin_created,
        report.admin_email,
    )
    print_next_steps(config.admin_email)
    _maybe_open_browser(MODELS_URL, enabled=config.open_browser and interactive)
    ensure_host_python_tooling(repo_root, quiet=True)
    return 0


def _run_init(args: argparse.Namespace) -> int:
    interactive = is_interactive() and not args.non_interactive
    _configure_logging(use_rich=interactive)
    try:
        repo_root = find_repo_root()
        if interactive:
            print_banner()
            print_intro()
        config = _load_config(args)
        updates: dict[str, object] = {}
        if args.skip_stack:
            updates["skip_stack"] = True
        updates["open_browser"] = _resolve_open_browser(config, no_browser_flag=args.no_browser)
        if updates:
            config = config.model_copy(update=updates)
        return run_init(config, repo_root=repo_root, interactive=interactive)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    except subprocess.CalledProcessError as exc:
        logger.error("Command failed with exit code %s: %s", exc.returncode, exc.cmd)
        return 1
    except TimeoutError as exc:
        logger.error("%s", exc)
        return 1
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        logger.error("Init failed: %s", exc)
        return 1
