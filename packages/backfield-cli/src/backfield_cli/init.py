"""Local first-run orchestration for Backfield."""

from __future__ import annotations

import argparse
import getpass
import logging
import subprocess
from pathlib import Path

from backfield_db.seed import DEFAULT_ORG_NAME, DEFAULT_STYLEBOOK_NAME, run_init_seed

from backfield_cli.credentials import resolve_admin_password
from backfield_cli.env_file import ensure_repo_env_file, find_repo_root, load_env_into_process
from backfield_cli.init_config import InitConfig, load_init_config
from backfield_cli.stack import (
    bring_up_stack,
    configure_host_database_env,
    run_compose_migrate,
    wait_for_api_readiness,
)

logger = logging.getLogger(__name__)

AGATE_UI_URL = "http://localhost:5173"
STYLEBOOK_UI_URL = "http://localhost:5175"
INTEGRATIONS_URL = f"{AGATE_UI_URL}/settings/integrations"


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
    parser.set_defaults(handler=_run_init)


def _prompt(text: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{text}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("A value is required.")


def _prompt_password(text: str) -> str:
    while True:
        value = getpass.getpass(f"{text}: ")
        if value:
            return value
        print("A value is required.")


def _load_config(args: argparse.Namespace) -> InitConfig:
    if args.non_interactive:
        if not args.config:
            raise ValueError("--non-interactive requires --config")
        return load_init_config(Path(args.config))
    if args.config:
        return load_init_config(Path(args.config))

    print("Backfield local init")
    admin_email = _prompt("Admin email")
    admin_password = _prompt_password("Admin password")
    admin_display_name = _prompt("Admin display name", default="Admin")
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


def run_init(config: InitConfig, *, repo_root: Path) -> int:
    env_report = ensure_repo_env_file(repo_root)
    if env_report.created_env_file:
        logger.info("Created %s", env_report.env_path)
    if env_report.generated_keys:
        logger.info("Generated env keys: %s", ", ".join(env_report.generated_keys))
    else:
        logger.info("Existing env secrets left unchanged")

    load_env_into_process(env_report.env_path)

    if not config.skip_stack:
        bring_up_stack(repo_root)
    else:
        logger.info("Skipping docker compose up (--skip-stack)")

    run_compose_migrate(repo_root)
    wait_for_api_readiness(repo_root)

    configure_host_database_env()
    admin_password = resolve_admin_password(
        password=config.admin_password,
        password_file=config.admin_password_file,
    )
    report = run_init_seed(
        org_slug=config.org_slug,
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
    _print_success(config.admin_email)
    return 0


def _print_success(admin_email: str) -> None:
    print()
    print("Backfield is ready.")
    print(f"  Agate UI:        {AGATE_UI_URL}")
    print(f"  Stylebook UI:    {STYLEBOOK_UI_URL}")
    print(f"  Integrations:    {INTEGRATIONS_URL}")
    print(f"  Admin login:     {admin_email}")
    print()
    print("Add API keys under Settings → Integrations in the Agate UI.")


def _run_init(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        repo_root = find_repo_root()
        config = _load_config(args)
        if args.skip_stack:
            config = config.model_copy(update={"skip_stack": True})
        return run_init(config, repo_root=repo_root)
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
