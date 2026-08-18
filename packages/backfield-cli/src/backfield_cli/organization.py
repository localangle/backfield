"""Trusted organization administration commands."""

from __future__ import annotations

import argparse
import logging

from pydantic import ValidationError

logger = logging.getLogger(__name__)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    organization = subparsers.add_parser(
        "organization",
        help="Manage complete Backfield organizations",
    )
    commands = organization.add_subparsers(
        dest="organization_command",
        required=True,
    )
    create = commands.add_parser(
        "create",
        help="Atomically create or verify a complete starter organization",
    )
    create.add_argument("--organization-name", required=True)
    create.add_argument("--organization-slug", required=True)
    create.add_argument("--stylebook-name", required=True)
    create.add_argument("--stylebook-slug", required=True)
    create.add_argument("--workspace-name", required=True)
    create.add_argument("--workspace-slug", required=True)
    create.add_argument("--project-name", required=True)
    create.add_argument("--project-slug", required=True)
    create.add_argument("--client-admin-email", required=True)
    create.add_argument("--support-admin-email")
    create.add_argument(
        "--temporary-password-file",
        required=True,
        help=(
            "JSON file with client_admin_password and optional "
            "support_admin_password; the file is only read"
        ),
    )
    create.add_argument(
        "--curated-model",
        action="append",
        required=True,
        dest="curated_models",
        help="Curated model id to snapshot; repeat for every selected model",
    )
    create.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable provisioning report",
    )
    create.set_defaults(handler=_run_create)


def _run_create(args: argparse.Namespace) -> int:
    from backfield_ai.curated_catalog import list_curated_templates
    from backfield_db.organization_provisioning import (
        OrganizationProvisioningRequest,
        StarterResourceInput,
        load_temporary_passwords,
        run_organization_provisioning,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        request = OrganizationProvisioningRequest(
            organization=StarterResourceInput(
                name=args.organization_name,
                slug=args.organization_slug,
            ),
            stylebook=StarterResourceInput(
                name=args.stylebook_name,
                slug=args.stylebook_slug,
            ),
            workspace=StarterResourceInput(
                name=args.workspace_name,
                slug=args.workspace_slug,
            ),
            project=StarterResourceInput(
                name=args.project_name,
                slug=args.project_slug,
            ),
            client_admin_email=args.client_admin_email,
            support_admin_email=args.support_admin_email,
            curated_model_ids=tuple(args.curated_models),
        )
        passwords = load_temporary_passwords(args.temporary_password_file)
        report = run_organization_provisioning(
            request,
            passwords,
            templates=list_curated_templates(),
        )
    except (ValidationError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        logger.error("Organization provisioning failed: %s", exc)
        return 1

    if args.json:
        print(report.to_json())
    else:
        action = "created" if report.organization_created else "reused"
        logger.info(
            "Organization %s organization_id=%s slug=%s stylebook_id=%s "
            "workspace_id=%s project_id=%s model_count=%s",
            action,
            report.organization_id,
            report.organization_slug,
            report.stylebook_id,
            report.workspace_id,
            report.project_id,
            len(report.model_config_ids),
        )
        for user in report.users:
            logger.info(
                "Administrator email=%s user_id=%s user_created=%s membership_created=%s",
                user.email,
                user.user_id,
                user.created,
                user.membership_created,
            )
    return 0
