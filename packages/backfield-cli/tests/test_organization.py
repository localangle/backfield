"""Tests for the trusted organization provisioning CLI."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from backfield_cli.main import main
from backfield_db.organization_provisioning import (
    OrganizationProvisioningReport,
    ProvisionedUserReport,
)


def _args(password_file: str) -> list[str]:
    return [
        "organization",
        "create",
        "--organization-name",
        "Acme News",
        "--organization-slug",
        "acme",
        "--stylebook-name",
        "Acme Stylebook",
        "--stylebook-slug",
        "acme-stylebook",
        "--workspace-name",
        "Acme Workspace",
        "--workspace-slug",
        "acme-workspace",
        "--project-name",
        "Acme Project",
        "--project-slug",
        "newsroom",
        "--client-admin-email",
        "ADMIN@Example.com",
        "--support-admin-email",
        "support@example.com",
        "--temporary-password-file",
        password_file,
        "--curated-model",
        "openai:gpt-5-nano",
        "--curated-model",
        "openai:text-embedding-3-small",
        "--json",
    ]


def _report() -> OrganizationProvisioningReport:
    return OrganizationProvisioningReport(
        organization_id=1,
        organization_slug="acme",
        organization_created=True,
        stylebook_id=2,
        stylebook_created=True,
        workspace_id=3,
        workspace_created=True,
        project_id=4,
        project_created=True,
        users=(
            ProvisionedUserReport(
                email="admin@example.com",
                user_id=5,
                created=True,
                membership_created=True,
            ),
            ProvisionedUserReport(
                email="support@example.com",
                user_id=6,
                created=False,
                membership_created=True,
            ),
        ),
        curated_model_ids=(
            "openai:gpt-5-nano",
            "openai:text-embedding-3-small",
        ),
        model_config_ids=("model-1", "model-2"),
    )


def test_organization_create_passes_explicit_inputs_and_prints_safe_json(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    client_secret = "client-secret-never-print"
    support_secret = "support-secret-never-print"
    password_file = tmp_path / "passwords.json"
    password_file.write_text(
        json.dumps(
            {
                "client_admin_password": client_secret,
                "support_admin_password": support_secret,
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(request, passwords):
        captured["request"] = request
        captured["passwords"] = passwords
        return _report()

    monkeypatch.setattr(
        "backfield_db.organization_provisioning.run_organization_provisioning",
        fake_run,
    )

    assert main(_args(str(password_file))) == 0
    request = captured["request"]
    assert request.organization.slug == "acme"
    assert request.client_admin_email == "admin@example.com"
    assert request.curated_model_ids == (
        "openai:gpt-5-nano",
        "openai:text-embedding-3-small",
    )
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["organization_id"] == 1
    assert payload["curated_model_ids"] == [
        "openai:gpt-5-nano",
        "openai:text-embedding-3-small",
    ]
    assert client_secret not in output.out + output.err
    assert support_secret not in output.out + output.err


def test_organization_create_rejects_missing_required_inputs(tmp_path) -> None:
    password_file = tmp_path / "passwords.json"
    password_file.write_text(
        json.dumps({"client_admin_password": "client-temporary-47"}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        main(
            [
                "organization",
                "create",
                "--organization-name",
                "Acme",
                "--temporary-password-file",
                str(password_file),
            ]
        )


def test_organization_create_rejects_invalid_password_file_without_leaking(
    tmp_path,
    capsys,
) -> None:
    leaked = "do-not-leak-this"
    password_file = tmp_path / "passwords.json"
    password_file.write_text(
        json.dumps(
            {
                "client_admin_password": leaked,
                "unexpected": "field",
            }
        ),
        encoding="utf-8",
    )

    assert main(_args(str(password_file))) == 1
    output = capsys.readouterr()
    assert leaked not in output.out + output.err


def test_organization_create_password_policy_error_does_not_leak_secret(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    secret = "password123"
    password_file = tmp_path / "passwords.json"
    password_file.write_text(
        json.dumps(
            {
                "client_admin_password": secret,
                "support_admin_password": "support-temporary-58",
            }
        ),
        encoding="utf-8",
    )

    def reject_weak_password(*_args):
        raise ValueError("Choose a stronger password")

    monkeypatch.setattr(
        "backfield_db.organization_provisioning.run_organization_provisioning",
        reject_weak_password,
    )
    messages: list[str] = []
    monkeypatch.setattr(
        "backfield_cli.organization.logger.error",
        lambda message, *args: messages.append(message % args),
    )

    assert main(_args(str(password_file))) == 1
    output = capsys.readouterr()
    assert messages == ["Choose a stronger password"]
    assert secret not in "".join(messages)
    assert secret not in output.out + output.err


def test_generic_production_entrypoint_is_packaged_in_agate_image() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    package_config = tomllib.loads(
        (repo_root / "packages/backfield-cli/pyproject.toml").read_text(encoding="utf-8")
    )
    assert package_config["project"]["scripts"]["backfield"] == "backfield_cli.main:main"

    dockerfile = (repo_root / "apps/agate-api/Dockerfile").read_text(encoding="utf-8")
    assert "packages/backfield-cli" in dockerfile
    assert "COPY --from=builder /usr/local/bin /usr/local/bin" in dockerfile
