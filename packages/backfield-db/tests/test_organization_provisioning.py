"""Tests for complete transactional organization provisioning."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime

import backfield_db.organization_provisioning as provisioning
import pytest
from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_db.organization_provisioning import (
    OrganizationProvisioningConflict,
    OrganizationProvisioningRequest,
    StarterResourceInput,
    TemporaryPasswordInput,
    load_temporary_passwords,
    provision_organization,
    run_organization_provisioning,
)
from backfield_db.passwords import hash_password, verify_password
from pydantic import SecretStr, ValidationError
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def sqlite_engine(tmp_path) -> Generator:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'provisioning.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine


def _request(
    *,
    organization_name: str = "Acme News",
    organization_slug: str = "acme",
    client_email: str = "CLIENT@Example.com ",
    support_email: str | None = None,
    models: tuple[str, ...] = (
        "openai:gpt-5-nano",
        "openai:text-embedding-3-small",
    ),
) -> OrganizationProvisioningRequest:
    return OrganizationProvisioningRequest(
        organization=StarterResourceInput(
            name=organization_name,
            slug=organization_slug,
        ),
        stylebook=StarterResourceInput(name="Acme Stylebook", slug="acme-stylebook"),
        workspace=StarterResourceInput(name="Acme Workspace", slug="acme-workspace"),
        project=StarterResourceInput(name="Acme Project", slug="newsroom"),
        client_admin_email=client_email,
        support_admin_email=support_email,
        curated_model_ids=models,
    )


def _passwords(*, support: str | None = None) -> TemporaryPasswordInput:
    return TemporaryPasswordInput(
        client_admin_password=SecretStr("client-temporary-47"),
        support_admin_password=SecretStr(support) if support is not None else None,
    )


def _provision_and_commit(
    session: Session,
    request: OrganizationProvisioningRequest,
    passwords: TemporaryPasswordInput,
) -> provisioning.OrganizationProvisioningReport:
    report = provision_organization(session, request, passwords)
    session.commit()
    return report


def test_provision_complete_organization_and_selected_models(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        report = _provision_and_commit(session, _request(), _passwords())

    assert report.organization_created is True
    assert report.stylebook_created is True
    assert report.workspace_created is True
    assert report.project_created is True
    assert report.curated_model_ids == (
        "openai:gpt-5-nano",
        "openai:text-embedding-3-small",
    )

    with Session(sqlite_engine) as session:
        organization = session.get(BackfieldOrganization, report.organization_id)
        stylebook = session.get(Stylebook, report.stylebook_id)
        workspace = session.get(BackfieldWorkspace, report.workspace_id)
        project = session.get(BackfieldProject, report.project_id)
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "client@example.com")
        ).one()
        membership = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.user_id == user.id,
                BackfieldOrganizationMembership.organization_id == organization.id,
            )
        ).one()
        model_rows = session.exec(
            select(BackfieldAiModelConfig).where(
                BackfieldAiModelConfig.organization_id == organization.id
            )
        ).all()

        assert organization is not None
        assert stylebook is not None and stylebook.is_default is True
        assert workspace is not None and workspace.stylebook_id == stylebook.id
        assert project is not None and project.workspace_id == workspace.id
        assert project.stylebook_id == stylebook.id
        assert membership.role == "org_admin"
        assert user.must_change_password is True
        assert verify_password("client-temporary-47", user.password_hash)
        assert {(row.provider, row.provider_model_id) for row in model_rows} == {
            ("openai", "gpt-5-nano"),
            ("openai", "text-embedding-3-small"),
        }
        assert all(row.integration_secret_id is None for row in model_rows)


def test_same_input_rerun_reuses_everything_and_preserves_password(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        first = _provision_and_commit(session, _request(), _passwords())
    with Session(sqlite_engine) as session:
        second = _provision_and_commit(
            session,
            _request(),
            TemporaryPasswordInput(
                client_admin_password=SecretStr("different-temporary-82")
            ),
        )

    assert second.reused is True
    assert second.organization_id == first.organization_id
    assert second.stylebook_id == first.stylebook_id
    assert second.workspace_id == first.workspace_id
    assert second.project_id == first.project_id
    assert set(second.model_config_ids) == set(first.model_config_ids)

    with Session(sqlite_engine) as session:
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "client@example.com")
        ).one()
        assert verify_password("client-temporary-47", user.password_hash)
        assert not verify_password("different-temporary-82", user.password_hash)


def test_existing_global_user_is_attached_without_password_change(sqlite_engine) -> None:
    original_hash = hash_password("existing-password-93")
    with Session(sqlite_engine) as session:
        session.add(
            BackfieldUser(
                email="Client@Example.com",
                password_hash=original_hash,
                must_change_password=False,
            )
        )
        session.commit()

    with Session(sqlite_engine) as session:
        report = _provision_and_commit(session, _request(), _passwords())

    assert report.users[0].created is False
    assert report.users[0].membership_created is True
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "Client@Example.com")
        ).one()
        assert user.password_hash == original_hash
        assert user.must_change_password is False


def test_optional_support_admin_is_created_and_visible(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        report = _provision_and_commit(
            session,
            _request(support_email="support@example.com"),
            _passwords(support="support-temporary-58"),
        )

    assert [user.email for user in report.users] == [
        "client@example.com",
        "support@example.com",
    ]
    with Session(sqlite_engine) as session:
        memberships = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.organization_id == report.organization_id
            )
        ).all()
        support = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "support@example.com")
        ).one()
        assert len(memberships) == 2
        assert {membership.role for membership in memberships} == {"org_admin"}
        assert support.must_change_password is True


def test_exact_support_admin_rerun_reuses_complete_admin_set(sqlite_engine) -> None:
    request = _request(support_email="support@example.com")
    with Session(sqlite_engine) as session:
        first = _provision_and_commit(
            session,
            request,
            _passwords(support="support-temporary-58"),
        )
    with Session(sqlite_engine) as session:
        second = _provision_and_commit(
            session,
            request,
            _passwords(support="different-support-temporary-76"),
        )
    assert second.reused is True
    assert second.organization_id == first.organization_id


def test_rerun_conflicts_when_requested_support_admin_is_omitted(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        _provision_and_commit(
            session,
            _request(support_email="support@example.com"),
            _passwords(support="support-temporary-58"),
        )
    with Session(sqlite_engine) as session:
        with pytest.raises(
            OrganizationProvisioningConflict,
            match="org_admin set does not match",
        ):
            provision_organization(session, _request(), _passwords())


def test_rerun_conflicts_when_support_admin_email_changes(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        _provision_and_commit(
            session,
            _request(support_email="support@example.com"),
            _passwords(support="support-temporary-58"),
        )
    with Session(sqlite_engine) as session:
        with pytest.raises(
            OrganizationProvisioningConflict,
            match="org_admin set does not match",
        ):
            provision_organization(
                session,
                _request(support_email="other-support@example.com"),
                _passwords(support="other-support-temporary-61"),
            )


def test_rerun_conflicts_with_unrequested_existing_org_admin(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        report = _provision_and_commit(session, _request(), _passwords())
    with Session(sqlite_engine) as session:
        extra = BackfieldUser(
            email="extra-admin@example.com",
            password_hash=hash_password("extra-admin-secret-42"),
        )
        session.add(extra)
        session.flush()
        session.add(
            BackfieldOrganizationMembership(
                user_id=int(extra.id),
                organization_id=report.organization_id,
                role="org_admin",
            )
        )
        session.commit()
    with Session(sqlite_engine) as session:
        with pytest.raises(
            OrganizationProvisioningConflict,
            match="org_admin set does not match",
        ):
            provision_organization(session, _request(), _passwords())


def test_missing_support_password_rolls_back_entire_new_organization(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        with pytest.raises(ValueError, match="temporary password is required"):
            provision_organization(
                session,
                _request(support_email="support@example.com"),
                _passwords(),
            )

    with Session(sqlite_engine) as session:
        assert session.exec(select(BackfieldOrganization)).all() == []
        assert session.exec(select(BackfieldProject)).all() == []
        assert session.exec(select(BackfieldUser)).all() == []


def test_service_leaves_transaction_completion_to_caller(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        session.add(BackfieldOrganization(name="Unrelated", slug="unrelated"))
        report = provision_organization(session, _request(), _passwords())
        assert report.organization_created is True
        session.rollback()

    with Session(sqlite_engine) as session:
        assert session.exec(select(BackfieldOrganization)).all() == []


def test_service_does_not_rollback_unrelated_caller_work_on_error(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        session.add(BackfieldOrganization(name="Unrelated", slug="unrelated"))
        with pytest.raises(ValueError, match="temporary password is required"):
            provision_organization(
                session,
                _request(support_email="support@example.com"),
                _passwords(),
            )
        unrelated = session.exec(
            select(BackfieldOrganization).where(
                BackfieldOrganization.slug == "unrelated"
            )
        ).one()
        assert unrelated.name == "Unrelated"
        session.rollback()


def test_existing_partial_or_conflicting_organization_fails_without_mutation(
    sqlite_engine,
) -> None:
    with Session(sqlite_engine) as session:
        session.add(BackfieldOrganization(name="Acme News", slug="acme"))
        session.commit()

    with Session(sqlite_engine) as session:
        with pytest.raises(
            OrganizationProvisioningConflict,
            match="missing the requested Stylebook",
        ):
            provision_organization(session, _request(), _passwords())

    with Session(sqlite_engine) as session:
        assert len(session.exec(select(BackfieldOrganization)).all()) == 1
        assert session.exec(select(Stylebook)).all() == []
        assert session.exec(select(BackfieldUser)).all() == []


def test_disabled_existing_user_is_rejected_for_create_and_rerun(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        session.add(
            BackfieldUser(
                email="client@example.com",
                password_hash=hash_password("existing-password-93"),
                disabled_at=datetime.now(UTC),
            )
        )
        session.commit()
    with Session(sqlite_engine) as session:
        with pytest.raises(OrganizationProvisioningConflict, match="is disabled"):
            provision_organization(session, _request(), _passwords())
        session.rollback()

    with Session(sqlite_engine) as session:
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "client@example.com")
        ).one()
        user.disabled_at = None
        session.add(user)
        session.commit()
    with Session(sqlite_engine) as session:
        _provision_and_commit(session, _request(), _passwords())
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "client@example.com")
        ).one()
        user.disabled_at = datetime.now(UTC)
        session.add(user)
        session.commit()
    with Session(sqlite_engine) as session:
        with pytest.raises(OrganizationProvisioningConflict, match="is disabled"):
            provision_organization(session, _request(), _passwords())


def test_new_admin_password_uses_shared_strength_policy_without_leaking(
    sqlite_engine,
) -> None:
    secret = "password123"
    passwords = TemporaryPasswordInput(client_admin_password=SecretStr(secret))
    with Session(sqlite_engine) as session:
        with pytest.raises(ValueError, match="stronger") as exc_info:
            provision_organization(session, _request(), passwords)
        session.rollback()
    assert secret not in str(exc_info.value)


def test_new_admin_password_policy_uses_normalized_email(sqlite_engine) -> None:
    secret = "clientadmin"
    passwords = TemporaryPasswordInput(client_admin_password=SecretStr(secret))
    with Session(sqlite_engine) as session:
        with pytest.raises(ValueError, match="email local part"):
            provision_organization(
                session,
                _request(client_email=" ClientAdmin@Example.com "),
                passwords,
            )
        session.rollback()


def test_new_admin_password_policy_enforces_shared_utf8_byte_limit(
    sqlite_engine,
) -> None:
    passwords = TemporaryPasswordInput(
        client_admin_password=SecretStr("é" * 37),
    )
    with Session(sqlite_engine) as session:
        with pytest.raises(ValueError, match="at most 72 UTF-8 bytes"):
            provision_organization(session, _request(), passwords)
        session.rollback()


def test_changed_curated_snapshot_conflicts_on_rerun(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        report = _provision_and_commit(session, _request(), _passwords())
    with Session(sqlite_engine) as session:
        row = session.get(BackfieldAiModelConfig, report.model_config_ids[0])
        assert row is not None
        row.status = "disabled"
        session.add(row)
        session.commit()
    with Session(sqlite_engine) as session:
        with pytest.raises(
            OrganizationProvisioningConflict,
            match="AI catalog does not match",
        ):
            provision_organization(session, _request(), _passwords())


def test_same_project_slug_is_allowed_in_different_organizations(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        first = _provision_and_commit(session, _request(), _passwords())
    with Session(sqlite_engine) as session:
        second = _provision_and_commit(
            session,
            _request(
                organization_name="Beta News",
                organization_slug="beta",
                client_email="beta@example.com",
            ),
            _passwords(),
        )
    assert first.project_id != second.project_id
    with Session(sqlite_engine) as session:
        projects = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "newsroom")
        ).all()
        assert len(projects) == 2


def test_isolated_runner_reloads_exact_concurrent_winner(
    sqlite_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(sqlite_engine) as session:
        expected = _provision_and_commit(session, _request(), _passwords())

    def lose_race(*_args, **_kwargs):
        raise provisioning.IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(provisioning, "create_direct_engine", lambda: sqlite_engine)
    monkeypatch.setattr(provisioning, "provision_organization", lose_race)
    report = run_organization_provisioning(_request(), _passwords())
    assert report.reused is True
    assert report.organization_id == expected.organization_id


def test_request_requires_explicit_nonempty_curated_selection() -> None:
    with pytest.raises(ValidationError):
        _request(models=())
    with pytest.raises(ValidationError, match="Unknown curated model"):
        _request(models=("not:a-model",))


def test_password_file_loader_is_strict_and_secret_safe(tmp_path) -> None:
    secret = "never-print-this-password"
    path = tmp_path / "passwords.json"
    path.write_text(
        json.dumps({"client_admin_password": secret}),
        encoding="utf-8",
    )
    passwords = load_temporary_passwords(path)
    assert passwords.client_admin_password.get_secret_value() == secret
    assert secret not in repr(passwords)
    assert secret not in passwords.model_dump_json()

    path.write_text(
        json.dumps({"client_admin_password": secret, "unexpected": "value"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be valid JSON") as exc_info:
        load_temporary_passwords(path)
    assert secret not in str(exc_info.value)


def test_password_file_loader_rejects_missing_and_invalid_files(tmp_path) -> None:
    with pytest.raises(ValueError, match="Could not read temporary password file"):
        load_temporary_passwords(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="must be valid JSON"):
        load_temporary_passwords(invalid)
