"""DBOutput → ``resolve_effective_stylebook_id`` bridge."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_stylebook.db_output_settings import resolve_effective_stylebook_id
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_db_output_resolve_unknown_project() -> None:
    engine = _engine()
    with Session(engine) as session:
        try:
            resolve_effective_stylebook_id(session, project_id=99999, stylebook_id_override=None)
        except ValueError as e:
            assert "not found" in str(e).lower()
        else:
            raise AssertionError("expected ValueError")


def test_db_output_delegates_override_to_shared_resolver() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-dbo", name="O")
        session.add(org)
        session.flush()
        sb_a = Stylebook(organization_id=int(org.id), slug="a", name="A", is_default=False)
        sb_b = Stylebook(organization_id=int(org.id), slug="b", name="B", is_default=True)
        session.add(sb_a)
        session.add(sb_b)
        session.flush()
        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            name="W",
            slug="w-dbo",
            stylebook_id=int(sb_b.id),
        )
        session.add(ws)
        session.flush()
        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="P",
            slug="p-dbo",
        )
        session.add(proj)
        session.commit()

        assert resolve_effective_stylebook_id(
            session,
            project_id=int(proj.id),
            stylebook_id_override=int(sb_a.id),
        ) == int(sb_a.id)
        assert resolve_effective_stylebook_id(
            session,
            project_id=int(proj.id),
            stylebook_id_override=None,
        ) == int(sb_b.id)
