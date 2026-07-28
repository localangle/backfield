"""Single-item runs: one ``agate_processed_item`` row and ingress shims."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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


def test_worker_cannot_store_output_after_cancellation(single_engine):
    engine, item_id, run_id = single_engine
    claimed_at = datetime.now(UTC)
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        item = session.get(AgateProcessedItem, item_id)
        assert run is not None
        assert item is not None
        run.status = "failed"
        run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
        item.status = "failed"
        item.started_at = claimed_at
        item.error_message = worker_tasks._RUN_CANCELLED_MESSAGE + " (was running)"
        session.add(run)
        session.add(item)
        session.commit()

        stored = worker_tasks._update_processed_item_outcome_if_active(
            session,
            item_id=item_id,
            run_id=run_id,
            claimed_at=claimed_at,
            status="succeeded",
            result_json='{"result":"late"}',
            substrate_article_id=None,
            error_message=None,
            now=datetime.now(UTC),
        )
        session.rollback()
        session.refresh(item)

        assert not stored
        assert item.status == "failed"
        assert item.error_message == worker_tasks._RUN_CANCELLED_MESSAGE + " (was running)"
        assert item.result_json is None


def test_stale_worker_cannot_complete_a_newer_claim(single_engine):
    engine, item_id, run_id = single_engine
    stale_claimed_at = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    newer_claimed_at = datetime(2026, 7, 20, 12, 5, tzinfo=UTC)
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        item = session.get(AgateProcessedItem, item_id)
        assert run is not None
        assert item is not None
        run.status = "running"
        item.status = "running"
        item.started_at = newer_claimed_at
        session.add(run)
        session.add(item)
        session.commit()

        stored = worker_tasks._update_processed_item_outcome_if_active(
            session,
            item_id=item_id,
            run_id=run_id,
            claimed_at=stale_claimed_at,
            status="succeeded",
            result_json='{"result":"stale"}',
            substrate_article_id=None,
            error_message=None,
            now=datetime.now(UTC),
        )
        session.rollback()
        session.refresh(item)

        assert not stored
        assert item.status == "running"
        assert item.started_at == newer_claimed_at.replace(tzinfo=None)
        assert item.result_json is None

    with pytest.raises(RuntimeError, match="claim is no longer active"):
        worker_tasks._ensure_processed_item_active(
            engine,
            run_id=run_id,
            item_id=item_id,
            claimed_at=stale_claimed_at,
        )


def test_between_node_check_stops_cancelled_run(single_engine):
    engine, _item_id, run_id = single_engine
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        run.status = "failed"
        run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
        session.add(run)
        session.commit()

    before_node, _after_node, _timings = worker_tasks._node_wall_clock_hooks(
        before_node_check=lambda: worker_tasks._ensure_parent_run_running(engine, run_id)
    )
    with pytest.raises(RuntimeError, match=worker_tasks._RUN_CANCELLED_MESSAGE):
        before_node("node-2", "Output")
