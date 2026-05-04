"""Catalog slug resolution for optional ``stylebook_slug`` override."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_stylebook.resolve import (
    STYLEBOOK_SLUG_NOT_IN_ORG,
    resolve_effective_stylebook_id_for_project,
    resolve_stylebook_id_for_project_id,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_effective_uses_workspace_when_slug_missing() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-eff", name="Org Eff")
        session.add(org)
        session.flush()

        sb_a = Stylebook(organization_id=int(org.id), slug="alpha", name="Alpha", is_default=False)
        sb_b = Stylebook(organization_id=int(org.id), slug="beta", name="Beta", is_default=True)
        session.add(sb_a)
        session.add(sb_b)
        session.flush()

        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            name="WS",
            slug="ws-eff",
            stylebook_id=int(sb_b.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-eff",
        )
        session.add(proj)
        session.commit()

        got = resolve_effective_stylebook_id_for_project(session, proj, stylebook_slug=None)
        assert got == int(sb_b.id)
        assert resolve_stylebook_id_for_project_id(session, int(proj.id)) == int(sb_b.id)


def test_effective_override_by_slug_same_org() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-eff2", name="Org Eff2")
        session.add(org)
        session.flush()

        sb_a = Stylebook(organization_id=int(org.id), slug="alpha", name="Alpha", is_default=False)
        sb_b = Stylebook(organization_id=int(org.id), slug="beta", name="Beta", is_default=True)
        session.add(sb_a)
        session.add(sb_b)
        session.flush()

        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            name="WS",
            slug="ws-eff2",
            stylebook_id=int(sb_b.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-eff2",
        )
        session.add(proj)
        session.commit()

        got = resolve_effective_stylebook_id_for_project(session, proj, stylebook_slug="alpha")
        assert got == int(sb_a.id)


def test_unknown_slug_raises() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-eff3", name="Org Eff3")
        session.add(org)
        session.flush()

        sb = Stylebook(organization_id=int(org.id), slug="only", name="Only", is_default=True)
        session.add(sb)
        session.flush()

        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            name="WS",
            slug="ws-eff3",
            stylebook_id=int(sb.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-eff3",
        )
        session.add(proj)
        session.commit()

        try:
            resolve_effective_stylebook_id_for_project(session, proj, stylebook_slug="nope")
        except LookupError as e:
            assert str(e) == STYLEBOOK_SLUG_NOT_IN_ORG
        else:
            raise AssertionError("expected LookupError")
