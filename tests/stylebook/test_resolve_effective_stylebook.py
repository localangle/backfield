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


def test_catalog_id_override_wins_workspace_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-cat", name="Org Cat")
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
            slug="ws-cat",
            stylebook_id=int(sb_b.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-cat",
        )
        session.add(proj)
        session.commit()

        got = resolve_effective_stylebook_id_for_project(
            session,
            proj,
            catalog_stylebook_id=int(sb_a.id),
        )
        assert got == int(sb_a.id)


def test_catalog_id_override_wins_slug() -> None:
    """Explicit integer catalog wins over ``stylebook_slug`` when both are set."""
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(slug="org-both", name="Org Both")
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
            slug="ws-both",
            stylebook_id=int(sb_b.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-both",
        )
        session.add(proj)
        session.commit()

        got = resolve_effective_stylebook_id_for_project(
            session,
            proj,
            stylebook_slug="beta",
            catalog_stylebook_id=int(sb_a.id),
        )
        assert got == int(sb_a.id)


def test_catalog_id_wrong_organization_raises() -> None:
    engine = _engine()
    with Session(engine) as session:
        org1 = BackfieldOrganization(slug="org1-c", name="O1")
        org2 = BackfieldOrganization(slug="org2-c", name="O2")
        session.add(org1)
        session.add(org2)
        session.flush()

        sb_foreign = Stylebook(
            organization_id=int(org2.id),
            slug="foreign",
            name="Foreign",
            is_default=True,
        )
        sb_home = Stylebook(
            organization_id=int(org1.id),
            slug="home",
            name="Home",
            is_default=True,
        )
        session.add(sb_foreign)
        session.add(sb_home)
        session.flush()

        ws = BackfieldWorkspace(
            organization_id=int(org1.id),
            name="WS",
            slug="ws-both-o",
            stylebook_id=int(sb_home.id),
        )
        session.add(ws)
        session.flush()

        proj = BackfieldProject(
            organization_id=int(org1.id),
            workspace_id=int(ws.id),
            name="Proj",
            slug="proj-both-o",
        )
        session.add(proj)
        session.commit()

        try:
            resolve_effective_stylebook_id_for_project(
                session,
                proj,
                catalog_stylebook_id=int(sb_foreign.id),
            )
        except ValueError as e:
            assert "organization" in str(e).lower()
        else:
            raise AssertionError("expected ValueError")
