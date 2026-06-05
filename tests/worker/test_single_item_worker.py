"""Single-item runs: one ``agate_processed_item`` row and ingress shims."""

from __future__ import annotations

import json

import pytest
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlmodel import Session, SQLModel, create_engine
from worker import tasks as worker_tasks


def _text_flow_spec() -> str:
    return json.dumps(
        {
            "name": "single_text",
            "nodes": [
                {"id": "t", "type": "TextInput", "params": {"text": "Hello Chicago."}},
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "t", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


@pytest.fixture
def single_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/single_item.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None

    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        ensure_default = __import__(
            "backfield_entities.catalog.bootstrap",
            fromlist=["ensure_default_stylebook_for_organization"],
        ).ensure_default_stylebook_for_organization
        ensure_default(s, organization_id=int(org.id))
        project = BackfieldProject(
            organization_id=int(org.id),
            name="Single",
            slug="single-item-worker",
        )
        s.add(project)
        s.commit()
        s.refresh(project)
        graph = AgateGraph(
            project_id=int(project.id),
            name="flow",
            spec_json=_text_flow_spec(),
        )
        s.add(graph)
        s.commit()
        s.refresh(graph)
        run = AgateRun(graph_id=graph.id, status="running")
        s.add(run)
        s.commit()
        s.refresh(run)
        item = AgateProcessedItem(
            run_id=run.id,
            source_file="inline:text",
            input_json=json.dumps({"text": "Hello Chicago."}),
            status="pending",
        )
        s.add(item)
        s.commit()
        s.refresh(item)
        yield engine, int(item.id), run.id
    db_session._engine = None


def test_execute_processed_item_text_input_shim(single_engine, monkeypatch):
    engine, item_id, run_id = single_engine
    monkeypatch.setattr(
        worker_tasks,
        "merge_project_and_org_llm_api_keys",
        lambda *_a, **_k: {},
    )

    worker_tasks.execute_processed_item(item_id)

    with Session(engine) as s:
        item = s.get(AgateProcessedItem, item_id)
        assert item is not None
        assert item.status == "succeeded"
        assert item.result_json is not None
        outputs = json.loads(item.result_json)
        assert "out" in outputs or any(k for k in outputs if k != "__outputKeysByNodeId")
        run = s.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "succeeded"
        wrap = json.loads(run.result_json or "{}")
        assert "items" in wrap
        assert len(wrap["items"]) == 1
