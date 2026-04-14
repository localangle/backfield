"""Tests for env-driven first admin bootstrap (core-api)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldUser
from core_api.bootstrap_users import ensure_first_org_admin
from core_api.env_bootstrap import run_env_bootstrap_if_configured
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def sqlite_engine_with_org(tmp_path) -> Generator:
    database_path = tmp_path / "env-bootstrap.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        org = BackfieldOrganization(name="Default", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        s.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
            )
        )
        s.commit()
    yield engine


@pytest.fixture
def sqlite_engine_empty_tables(tmp_path) -> Generator:
    database_path = tmp_path / "empty.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine


def test_ensure_first_org_admin_creates_and_idempotent(
    sqlite_engine_with_org,
) -> None:
    with Session(sqlite_engine_with_org) as session:
        r1 = ensure_first_org_admin(
            session,
            "admin@example.com",
            "secret-password",
            "Admin",
        )
        assert r1 is not None
        assert r1.get("ok") is True
        uid = r1["user_id"]

        r2 = ensure_first_org_admin(session, "other@example.com", "x", None)
        assert r2 is None

        u = session.exec(select(BackfieldUser).where(BackfieldUser.id == uid)).first()
        assert u is not None
        assert u.email == "admin@example.com"


def test_run_env_bootstrap_creates_user(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
) -> None:
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "1")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "env@example.com")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", "pw-env-test")
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    run_env_bootstrap_if_configured()

    with Session(sqlite_engine_with_org) as session:
        u = session.exec(select(BackfieldUser)).first()
        assert u is not None
        assert u.email == "env@example.com"


def test_run_env_bootstrap_second_start_skips(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
) -> None:
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "true")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "env2@example.com")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", "pw")
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    run_env_bootstrap_if_configured()
    run_env_bootstrap_if_configured()

    with Session(sqlite_engine_with_org) as session:
        users = session.exec(select(BackfieldUser)).all()
        assert len(users) == 1
        assert users[0].email == "env2@example.com"


def test_run_env_bootstrap_password_file(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
    tmp_path,
) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "1")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "file@example.com")
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(pw_file))
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    run_env_bootstrap_if_configured()

    with Session(sqlite_engine_with_org) as session:
        u = session.exec(select(BackfieldUser)).first()
        assert u is not None
        assert u.email == "file@example.com"


def test_run_env_bootstrap_flag_off_no_op(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
) -> None:
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", raising=False)
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "x@y.z")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", "pw")
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    run_env_bootstrap_if_configured()

    with Session(sqlite_engine_with_org) as session:
        assert session.exec(select(BackfieldUser)).first() is None


def test_run_env_bootstrap_strict_missing_password_exits(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
) -> None:
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "yes")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "a@b.c")
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    with pytest.raises(SystemExit) as excinfo:
        run_env_bootstrap_if_configured()
    assert excinfo.value.code == 1


def test_run_env_bootstrap_lenient_missing_password_no_exit(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_with_org,
) -> None:
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "1")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "a@b.c")
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_STRICT", "0")
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_with_org,
    )
    run_env_bootstrap_if_configured()
    with Session(sqlite_engine_with_org) as session:
        assert session.exec(select(BackfieldUser)).first() is None


def test_run_env_bootstrap_org_missing_exits(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine_empty_tables,
) -> None:
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV", "1")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD", "pw")
    monkeypatch.setattr(
        "core_api.env_bootstrap.get_engine",
        lambda: sqlite_engine_empty_tables,
    )
    with pytest.raises(SystemExit) as excinfo:
        run_env_bootstrap_if_configured()
    assert excinfo.value.code == 1
