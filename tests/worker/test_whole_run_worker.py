from __future__ import annotations

import json
import os

from backfield_db import (
    AgateGraph,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine
from worker import tasks as worker_tasks


def test_whole_run_sets_organization_context_and_fails_cleanly(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path}/whole-run.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization = BackfieldOrganization(name="Whole Run", slug="whole-run")
        session.add(organization)
        session.commit()
        session.refresh(organization)
        organization_id = int(organization.id)
        stylebook = ensure_default_stylebook_for_organization(session, organization_id)
        workspace = BackfieldWorkspace(
            organization_id=organization_id,
            stylebook_id=int(stylebook.id),
            name="Whole Run",
            slug="whole-run",
        )
        session.add(workspace)
        session.flush()
        project = BackfieldProject(
            organization_id=organization_id,
            workspace_id=int(workspace.id),
            stylebook_id=int(stylebook.id),
            name="Whole Run",
            slug="whole-run",
        )
        session.add(project)
        session.flush()
        graph = AgateGraph(
            project_id=int(project.id),
            name="Whole Run",
            spec_json=json.dumps(
                {
                    "name": "whole_run",
                    "nodes": [
                        {"id": "text", "type": "TextInput", "params": {"text": "Hello"}},
                        {"id": "output", "type": "Output", "params": {}},
                    ],
                    "edges": [
                        {
                            "source": "text",
                            "target": "output",
                            "sourceHandle": "text",
                            "targetHandle": "data",
                        }
                    ],
                }
            ),
        )
        session.add(graph)
        session.flush()
        successful = AgateRun(graph_id=graph.id, status="pending")
        failed = AgateRun(graph_id=graph.id, status="pending")
        session.add(successful)
        session.add(failed)
        session.commit()
        successful_id = str(successful.id)
        failed_id = str(failed.id)

    monkeypatch.setattr(worker_tasks, "get_engine", lambda: engine)
    monkeypatch.setattr(
        worker_tasks,
        "merge_project_and_org_llm_api_keys",
        lambda *_args, **_kwargs: {},
    )

    def execute_with_context(*_args, **_kwargs):
        assert os.environ["BACKFIELD_ORGANIZATION_ID"] == str(organization_id)
        return {"output": {"data": "done"}}

    monkeypatch.setattr(worker_tasks, "execute_graph", execute_with_context)
    worker_tasks.execute_agate_run(successful_id)
    assert "BACKFIELD_ORGANIZATION_ID" not in os.environ

    with Session(engine) as session:
        successful_row = session.get(AgateRun, successful_id)
        assert successful_row is not None
        assert successful_row.status == "succeeded"

    monkeypatch.setattr(
        worker_tasks,
        "merge_project_and_org_llm_api_keys",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("setup failed")),
    )
    worker_tasks.execute_agate_run(failed_id)
    with Session(engine) as session:
        failed_row = session.get(AgateRun, failed_id)
        assert failed_row is not None
        assert failed_row.status == "failed"
        assert failed_row.error_message == "setup failed"
