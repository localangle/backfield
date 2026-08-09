"""Domain tests for project / workspace teardown."""

from __future__ import annotations

import json
import uuid

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    BackfieldApiCredential,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldProjectSecret,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateArticle,
)
from backfield_entities.catalog.project_teardown import (
    ProjectTeardownError,
    delete_project,
    delete_workspace,
    project_delete_preview,
)
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_org(session: Session) -> tuple[int, int, int]:
    org = BackfieldOrganization(name="O", slug="o-teardown")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)
    sb = Stylebook(
        organization_id=oid,
        slug="default",
        name="Default Stylebook",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)
    ws = BackfieldWorkspace(
        organization_id=oid,
        stylebook_id=sb_id,
        name="Newsroom",
        slug="newsroom",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    return oid, sb_id, int(ws.id)


def test_delete_project_removes_flows_items_articles_keeps_canonical() -> None:
    engine = _engine()
    with Session(engine) as session:
        oid, sb_id, wid = _seed_org(session)
        project = BackfieldProject(
            **project_ownership_fields(session, oid, workspace_id=wid),
            organization_id=oid,
            workspace_id=wid,
            name="Demo Project",
            slug="demo-project",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        pid = int(project.id)

        canonical = StylebookLocationCanonical(
            id=str(uuid.uuid4()),
            stylebook_id=sb_id,
            label="City Hall",
            slug="city-hall",
            status="active",
        )
        session.add(canonical)
        session.flush()

        graph = AgateGraph(
            name="Flow A",
            spec_json=json.dumps({"name": "Flow A", "nodes": [], "edges": []}),
            project_id=pid,
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        run = AgateRun(graph_id=str(graph.id), status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            AgateProcessedItem(
                run_id=str(run.id),
                status="succeeded",
                input_json="{}",
                result_json="{}",
            )
        )
        session.add(
            BackfieldAiCallRecord(
                project_id=pid,
                run_id=str(run.id),
                provider="test",
                provider_model_id="m",
                status="succeeded",
            )
        )
        session.add(
            SubstrateArticle(
                project_id=pid,
                headline="Hello",
                text="Body",
                source_run_id=str(run.id),
            )
        )
        session.add(
            BackfieldApiCredential(
                project_id=pid,
                credential_type="service",
                key_prefix="bfk_test",
                key_hash="hash",
                scopes="read",
            )
        )
        session.add(
            BackfieldProjectSecret(
                project_id=pid,
                key="API_TOKEN",
                value_encrypted="enc",
            )
        )
        session.commit()

        preview = project_delete_preview(session, pid)
        assert preview is not None
        assert preview.flow_count == 1
        assert preview.run_count == 1
        assert preview.processed_item_count == 1
        assert preview.article_count == 1
        assert preview.api_credential_count == 1
        assert preview.secret_count == 1

        delete_project(session, pid)
        session.commit()

        assert session.get(BackfieldProject, pid) is None
        assert session.exec(select(AgateGraph).where(AgateGraph.project_id == pid)).first() is None
        assert (
            session.exec(select(SubstrateArticle).where(SubstrateArticle.project_id == pid)).first()
            is None
        )
        assert (
            session.exec(
                select(BackfieldApiCredential).where(BackfieldApiCredential.project_id == pid)
            ).first()
            is None
        )
        retained = session.get(StylebookLocationCanonical, canonical.id)
        assert retained is not None
        assert str(retained.label) == "City Hall"


def test_delete_general_project_blocked() -> None:
    engine = _engine()
    with Session(engine) as session:
        oid, sb_id, wid = _seed_org(session)
        project = BackfieldProject(
            **project_ownership_fields(session, oid, workspace_id=wid),
            organization_id=oid,
            workspace_id=wid,
            name="General",
            slug="general",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        try:
            delete_project(session, int(project.id))
        except ProjectTeardownError as err:
            assert "general" in str(err).lower()
        else:
            raise AssertionError("expected ProjectTeardownError")


def test_delete_workspace_blocked_when_contains_general() -> None:
    engine = _engine()
    with Session(engine) as session:
        oid, _sb_id, wid = _seed_org(session)
        session.add(
            BackfieldProject(
                **project_ownership_fields(session, oid, workspace_id=wid),
                organization_id=oid,
                workspace_id=wid,
                name="General",
                slug="general",
            )
        )
        session.add(
            BackfieldProject(
                **project_ownership_fields(session, oid, workspace_id=wid),
                organization_id=oid,
                workspace_id=wid,
                name="Extra",
                slug="extra",
            )
        )
        session.commit()

        try:
            delete_workspace(session, organization_id=oid, workspace_id=wid)
        except ProjectTeardownError as err:
            assert "general" in str(err).lower()
        else:
            raise AssertionError("expected ProjectTeardownError")

        assert session.get(BackfieldWorkspace, wid) is not None


def test_delete_workspace_cascades_projects() -> None:
    engine = _engine()
    with Session(engine) as session:
        oid, sb_id, wid = _seed_org(session)
        p1 = BackfieldProject(
            **project_ownership_fields(session, oid, workspace_id=wid),
            organization_id=oid,
            workspace_id=wid,
            name="One",
            slug="one",
        )
        p2 = BackfieldProject(
            **project_ownership_fields(session, oid, workspace_id=wid),
            organization_id=oid,
            workspace_id=wid,
            name="Two",
            slug="two",
        )
        session.add(p1)
        session.add(p2)
        session.commit()
        session.refresh(p1)
        session.refresh(p2)
        p1_id = int(p1.id)
        p2_id = int(p2.id)

        delete_workspace(session, organization_id=oid, workspace_id=wid)
        session.commit()

        assert session.get(BackfieldWorkspace, wid) is None
        assert session.get(BackfieldProject, p1_id) is None
        assert session.get(BackfieldProject, p2_id) is None
        assert session.get(Stylebook, sb_id) is not None
