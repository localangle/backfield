"""Seed subcommand for initial organization and admin provisioning."""

from __future__ import annotations

import argparse
import logging
import sys

from backfield_cli.credentials import resolve_admin_password

logger = logging.getLogger(__name__)

# Match backfield_db.seed defaults; keep argparse registration free of backfield_db imports.
_DEFAULT_ORG_SLUG = "default"
_DEFAULT_ORG_NAME = "Backfield"


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "seed",
        help="Ensure initial organization and admin user exist (idempotent)",
    )
    parser.add_argument(
        "--org-slug",
        default=_DEFAULT_ORG_SLUG,
        help=f"Organization slug to ensure (default: {_DEFAULT_ORG_SLUG})",
    )
    parser.add_argument(
        "--org-name",
        default=_DEFAULT_ORG_NAME,
        help=f"Organization display name when creating (default: {_DEFAULT_ORG_NAME})",
    )
    parser.add_argument("--admin-email", required=True, help="Admin user email to ensure")
    parser.add_argument(
        "--admin-password",
        default=None,
        help="Admin password when creating the user (omit if using --admin-password-file)",
    )
    parser.add_argument(
        "--admin-password-file",
        default=None,
        help="Path to a file containing the admin password",
    )
    parser.add_argument(
        "--admin-display-name",
        default=None,
        help="Optional display name when creating the admin user",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the seed report as JSON on stdout",
    )
    parser.set_defaults(handler=_run_seed)


def _run_seed(args: argparse.Namespace) -> int:
    from backfield_db.seed import run_seed

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        admin_password = resolve_admin_password(
            password=args.admin_password,
            password_file=args.admin_password_file,
            env_password=None,
        )
        report = run_seed(
            org_slug=args.org_slug,
            org_name=args.org_name,
            admin_email=args.admin_email,
            admin_password=admin_password,
            admin_display_name=args.admin_display_name,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        logger.error("Seed failed: %s", exc)
        return 1

    if args.json:
        print(report.to_json())
    else:
        logger.info(
            "Seed complete organization_id=%s organization_created=%s admin_user_id=%s "
            "admin_created=%s admin_email=%s",
            report.organization_id,
            report.organization_created,
            report.admin_user_id,
            report.admin_created,
            report.admin_email,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="backfield-seed")
    subparsers = parser.add_subparsers(dest="command", required=False)
    register_subcommand(subparsers)
    args = parser.parse_args()
    if getattr(args, "handler", None) is None:
        parser.error("seed command required")
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
