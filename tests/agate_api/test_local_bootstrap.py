"""Local bootstrap must not overwrite user-edited org/workspace display names."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from api.local_bootstrap import _ensure_default_workspace_and_general, run_local_bootstrap
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def bootstrap_engine(tmp_path) -> Generator:
    database_path = tmp_path / "local-bootstrap.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[
            BackfieldOrganization.__table__,
            BackfieldProject.__table__,
            BackfieldWorkspace.__table__,
            Stylebook.__table__,
        ],
    )
    yield engine


def test_ensure_default_workspace_preserves_organization_name(bootstrap_engine) -> None:
    with Session(bootstrap_engine) as session:
        org = BackfieldOrganization(name="Chicago Tribune", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        session.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
            )
        )
        session.commit()

        _ensure_default_workspace_and_general(session)
        session.commit()

        refreshed = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        assert refreshed.name == "Chicago Tribune"


def test_ensure_default_workspace_preserves_workspace_name(bootstrap_engine) -> None:
    with Session(bootstrap_engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        sb = Stylebook(
            organization_id=int(org.id),
            slug="default",
            name="Default Stylebook",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            stylebook_id=int(sb.id),
            name="Newsroom",
            slug="default",
        )
        session.add(ws)
        session.flush()
        session.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
                workspace_id=int(ws.id),
            )
        )
        session.commit()

        _ensure_default_workspace_and_general(session)
        session.commit()

        refreshed = session.exec(
            select(BackfieldWorkspace).where(BackfieldWorkspace.slug == "default")
        ).one()
        assert refreshed.name == "Newsroom"


def test_run_local_bootstrap_preserves_organization_name(bootstrap_engine) -> None:
    with Session(bootstrap_engine) as session:
        org = BackfieldOrganization(name="Daily Herald", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        session.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
            )
        )
        session.commit()

    with patch("api.local_bootstrap.get_engine", return_value=bootstrap_engine):
        run_local_bootstrap()

    with Session(bootstrap_engine) as session:
        refreshed = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        assert refreshed.name == "Daily Herald"
