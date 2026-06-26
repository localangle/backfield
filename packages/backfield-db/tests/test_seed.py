"""Tests for production-safe org/admin seeding."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization, BackfieldOrganizationMembership, BackfieldUser
from backfield_db.passwords import verify_password
from backfield_db.seed import ensure_initial_org_and_admin
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def sqlite_engine(tmp_path) -> Generator:
    database_path = tmp_path / "seed.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine


def test_ensure_initial_org_and_admin_creates_org_and_user(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        report = ensure_initial_org_and_admin(
            session,
            org_slug="acme",
            org_name="Acme News",
            admin_email="admin@example.com",
            admin_password="secret-password",
            admin_display_name="Admin",
        )

    assert report.organization_created is True
    assert report.admin_created is True
    assert report.organization_slug == "acme"
    assert report.admin_email == "admin@example.com"

    with Session(sqlite_engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "acme")
        ).one()
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "admin@example.com")
        ).one()
        membership = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.user_id == user.id,
                BackfieldOrganizationMembership.organization_id == org.id,
            )
        ).one()
        assert membership.role == "org_admin"
        assert verify_password("secret-password", user.password_hash)


def test_ensure_initial_org_and_admin_is_idempotent_and_preserves_password(
    sqlite_engine,
) -> None:
    with Session(sqlite_engine) as session:
        first = ensure_initial_org_and_admin(
            session,
            org_slug="acme",
            org_name="Acme News",
            admin_email="admin@example.com",
            admin_password="first-password",
            admin_display_name="Admin",
        )
        second = ensure_initial_org_and_admin(
            session,
            org_slug="acme",
            org_name="Renamed Org",
            admin_email="admin@example.com",
            admin_password="second-password",
            admin_display_name="Other Name",
        )

    assert first.organization_created is True
    assert first.admin_created is True
    assert second.organization_created is False
    assert second.admin_created is False

    with Session(sqlite_engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "acme")
        ).one()
        user = session.exec(
            select(BackfieldUser).where(BackfieldUser.email == "admin@example.com")
        ).one()
        assert org.name == "Acme News"
        assert user.display_name == "Admin"
        assert verify_password("first-password", user.password_hash)
        assert not verify_password("second-password", user.password_hash)


def test_ensure_initial_org_and_admin_uses_existing_org(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        session.add(BackfieldOrganization(name="Backfield", slug="default"))
        session.commit()

    with Session(sqlite_engine) as session:
        report = ensure_initial_org_and_admin(
            session,
            org_slug="default",
            org_name="Ignored Name",
            admin_email="admin@example.com",
            admin_password="secret-password",
        )

    assert report.organization_created is False
    assert report.admin_created is True

    with Session(sqlite_engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        assert org.name == "Backfield"


def test_apply_init_display_names_updates_migration_defaults(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        organization_id = int(org.id)

    with Session(sqlite_engine) as session:
        from backfield_db import Stylebook
        from backfield_db.seed import DEFAULT_STYLEBOOK_NAME, apply_init_display_names

        session.add(
            Stylebook(
                organization_id=organization_id,
                slug="default",
                name=DEFAULT_STYLEBOOK_NAME,
                is_default=True,
            )
        )
        session.commit()

    with Session(sqlite_engine) as session:
        from backfield_db.seed import apply_init_display_names

        apply_init_display_names(
            session,
            organization_id=organization_id,
            org_name="Acme News",
            stylebook_name="Acme Stylebook",
        )

    with Session(sqlite_engine) as session:
        from backfield_db import Stylebook

        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.id == organization_id)
        ).one()
        stylebook = session.exec(
            select(Stylebook).where(Stylebook.organization_id == org.id)
        ).one()
        assert org.name == "Acme News"
        assert org.slug == "acme-news"
        assert stylebook.name == "Acme Stylebook"
        assert stylebook.slug == "acme-stylebook"


def test_apply_init_display_names_leaves_renamed_org_unchanged(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        org = BackfieldOrganization(name="Renamed Org", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        organization_id = int(org.id)

    with Session(sqlite_engine) as session:
        from backfield_db.seed import apply_init_display_names

        apply_init_display_names(
            session,
            organization_id=organization_id,
            org_name="Acme News",
            stylebook_name="Acme Stylebook",
        )

    with Session(sqlite_engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        assert org.name == "Renamed Org"
        assert org.slug == "default"


def test_apply_init_display_names_updates_slug_after_partial_name_change(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        org = BackfieldOrganization(name="Acme News", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        organization_id = int(org.id)

    with Session(sqlite_engine) as session:
        from backfield_db import Stylebook
        from backfield_db.seed import DEFAULT_STYLEBOOK_NAME, apply_init_display_names

        session.add(
            Stylebook(
                organization_id=organization_id,
                slug="default",
                name=DEFAULT_STYLEBOOK_NAME,
                is_default=True,
            )
        )
        session.commit()

    with Session(sqlite_engine) as session:
        from backfield_db.seed import apply_init_display_names

        apply_init_display_names(
            session,
            organization_id=organization_id,
            org_name="Acme News",
            stylebook_name="Acme Stylebook",
        )

    with Session(sqlite_engine) as session:
        from backfield_db import Stylebook

        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.id == organization_id)
        ).one()
        stylebook = session.exec(
            select(Stylebook).where(Stylebook.organization_id == org.id)
        ).one()
        assert org.name == "Acme News"
        assert org.slug == "acme-news"
        assert stylebook.name == "Acme Stylebook"
        assert stylebook.slug == "acme-stylebook"


def test_run_init_seed_slugifies_org_and_stylebook(sqlite_engine, monkeypatch) -> None:
    monkeypatch.setattr("backfield_db.seed.get_engine", lambda: sqlite_engine)

    from backfield_db.seed import run_init_seed

    report = run_init_seed(
        org_name="Acme News",
        stylebook_name="Acme Stylebook",
        admin_email="admin@example.com",
        admin_password="secret-password",
    )

    assert report.organization_slug == "acme-news"

    with Session(sqlite_engine) as session:
        from backfield_db import Stylebook

        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "acme-news")
        ).one()
        stylebook = session.exec(
            select(Stylebook).where(Stylebook.organization_id == org.id)
        ).one()
        assert org.name == "Acme News"
        assert stylebook.name == "Acme Stylebook"
        assert stylebook.slug == "acme-stylebook"
