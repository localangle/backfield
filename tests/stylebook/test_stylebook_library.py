"""Tests for org stylebook library domain helpers."""

from __future__ import annotations

import json
import uuid

from backfield_db import (
    AgateGraph,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    StylebookBundleJob,
    StylebookSlugRedirect,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.graph_stylebook_refs import (
    STYLEBOOK_NODE_PARAM_KEY,
    validate_stylebook_refs_for_organization,
)
from backfield_stylebook.stylebook_library import (
    StylebookLibraryError,
    create_stylebook,
    delete_stylebook,
    rename_stylebook,
    resolve_stylebook_by_slug,
    set_org_default_stylebook,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_create_rejects_duplicate_name() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-lib")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        create_stylebook(session, organization_id=oid, name="Book A", is_default=True)
        session.commit()
        try:
            create_stylebook(session, organization_id=oid, name="Book A", is_default=False)
        except StylebookLibraryError as e:
            assert "name" in str(e).lower()
        else:
            raise AssertionError("expected StylebookLibraryError")


def test_rename_inserts_redirect_and_resolves_old_slug() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-re")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        a = create_stylebook(session, organization_id=oid, name="First", is_default=True)
        session.commit()
        session.refresh(a)
        aid = int(a.id)  # type: ignore[arg-type]
        old_slug = str(a.slug)

        rename_stylebook(session, stylebook_id=aid, new_name="Renamed Title")
        session.commit()

        rows = session.exec(select(StylebookSlugRedirect)).all()
        assert len(rows) == 1
        assert rows[0].old_slug == old_slug

        resolved = resolve_stylebook_by_slug(session, organization_id=oid, slug=old_slug)
        assert resolved is not None
        assert resolved.name == "Renamed Title"


def test_set_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-def")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        a = create_stylebook(session, organization_id=oid, name="A", is_default=True)
        b = create_stylebook(session, organization_id=oid, name="B", is_default=False)
        session.commit()
        session.refresh(a)
        session.refresh(b)
        bid = int(b.id)  # type: ignore[arg-type]

        set_org_default_stylebook(session, organization_id=oid, stylebook_id=bid)
        session.commit()
        session.refresh(a)
        session.refresh(b)
        assert b.is_default is True
        assert a.is_default is False


def test_cannot_delete_last_stylebook() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-del")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        sb = ensure_default_stylebook_for_organization(session, oid)
        session.commit()
        sid = int(sb.id)  # type: ignore[arg-type]
        try:
            delete_stylebook(session, sid)
        except StylebookLibraryError as e:
            assert "last" in str(e).lower()
        else:
            raise AssertionError("expected StylebookLibraryError")


def test_delete_reassigns_workspaces_to_org_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-ws")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        a = create_stylebook(session, organization_id=oid, name="A", is_default=True)
        b = create_stylebook(session, organization_id=oid, name="B", is_default=False)
        session.commit()
        session.refresh(a)
        session.refresh(b)
        aid = int(a.id)  # type: ignore[arg-type]
        bid = int(b.id)  # type: ignore[arg-type]

        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=bid,
            name="W",
            slug="w-x",
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        wid = int(ws.id)  # type: ignore[arg-type]

        delete_stylebook(session, bid)
        session.commit()

        assert session.get(Stylebook, bid) is None
        ws2 = session.get(BackfieldWorkspace, wid)
        assert ws2 is not None
        assert int(ws2.stylebook_id) == aid


def test_delete_reassigns_graph_node_stylebook_refs() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-graph")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        a = create_stylebook(session, organization_id=oid, name="A", is_default=True)
        b = create_stylebook(session, organization_id=oid, name="B", is_default=False)
        session.commit()
        session.refresh(a)
        session.refresh(b)
        aid = int(a.id)  # type: ignore[arg-type]
        bid = int(b.id)  # type: ignore[arg-type]

        proj = BackfieldProject(
            organization_id=oid,
            name="P",
            slug="p-graph",
            workspace_id=None,
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]

        spec = {
            "name": "flow",
            "nodes": [
                {
                    "id": "backfield",
                    "type": "db_output",
                    "params": {STYLEBOOK_NODE_PARAM_KEY: bid},
                },
            ],
            "edges": [],
        }
        graph = AgateGraph(name="G", spec_json=json.dumps(spec), project_id=pid)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

        delete_stylebook(session, bid)
        session.commit()

        updated = session.get(AgateGraph, gid)
        assert updated is not None
        updated_spec = json.loads(updated.spec_json)
        assert updated_spec["nodes"][0]["params"][STYLEBOOK_NODE_PARAM_KEY] == aid
        validate_stylebook_refs_for_organization(session, organization_id=oid, spec=updated_spec)


def test_delete_stylebook_removes_referencing_bundle_jobs() -> None:
    """Bundle import/export jobs FK to stylebook; delete must clear them first."""
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-bjob")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        create_stylebook(session, organization_id=oid, name="A", is_default=True)
        b = create_stylebook(session, organization_id=oid, name="B", is_default=False)
        session.commit()
        session.refresh(b)
        bid = int(b.id)  # type: ignore[arg-type]

        session.add(
            StylebookBundleJob(
                id=str(uuid.uuid4()),
                organization_id=oid,
                kind="import",
                status="succeeded",
                result_stylebook_id=bid,
            )
        )
        session.commit()

        delete_stylebook(session, bid)
        session.commit()

        assert session.get(Stylebook, bid) is None
        remaining_jobs = session.exec(select(StylebookBundleJob)).all()
        assert len(remaining_jobs) == 0


def test_delete_default_with_replacement() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-rep")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        a = create_stylebook(session, organization_id=oid, name="A", is_default=True)
        b = create_stylebook(session, organization_id=oid, name="B", is_default=False)
        session.commit()
        session.refresh(a)
        session.refresh(b)
        aid = int(a.id)  # type: ignore[arg-type]
        bid = int(b.id)  # type: ignore[arg-type]

        delete_stylebook(session, aid, replacement_default_id=bid)
        session.commit()

        rest = session.exec(select(Stylebook).where(Stylebook.organization_id == oid)).all()
        assert len(rest) == 1
        assert rest[0].id == bid
        assert rest[0].is_default is True


def test_ensure_default_still_idempotent() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-boot")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        x = ensure_default_stylebook_for_organization(session, oid)
        y = ensure_default_stylebook_for_organization(session, oid)
        assert x.id == y.id
