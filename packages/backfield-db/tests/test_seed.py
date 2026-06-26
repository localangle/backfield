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
