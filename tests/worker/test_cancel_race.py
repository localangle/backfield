"""Cancellation vs worker finalization race coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

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
from worker.terminal_transitions import apply_item_terminal_status


def _text_flow_spec() -> str:
    return json.dumps(
        {
            "name": "cancel_race",
            "nodes": [
                {"id": "t", "type": "TextInput", "params": {"text": "Hello."}},
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "t", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


@pytest.fixture
def race_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/cancel_race.db"
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
            name="Cancel",
            slug="cancel-race",
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
            input_json=json.dumps({"text": "Hello."}),
            status="pending",
        )
        s.add(item)
        s.commit()
        s.refresh(item)
        yield engine, int(item.id), run.id
    db_session._engine = None


def test_apply_item_terminal_does_not_overwrite_cancelled(race_engine):
    engine, item_id, _run_id = race_engine
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        item.status = "running"
        item.started_at = datetime.now(UTC)
        session.add(item)
        session.commit()
        session.refresh(item)
        item.status = "failed"
        item.error_message = worker_tasks._RUN_CANCELLED_MESSAGE + " (was running)"
        session.add(item)
        session.commit()
        session.refresh(item)
        applied = apply_item_terminal_status(
            session,
            item,
            new_status="succeeded",
            error_message=None,
            result_json=json.dumps({"ok": True}),
        )
        assert applied is False
        session.refresh(item)
        assert item.status == "failed"
        assert item.error_message and item.error_message.startswith(
            worker_tasks._RUN_CANCELLED_MESSAGE
        )


def test_finalize_preserves_cancelled_run(race_engine):
    engine, item_id, run_id = race_engine
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        run = session.get(AgateRun, run_id)
        assert item is not None and run is not None
        item.status = "failed"
        item.error_message = worker_tasks._RUN_CANCELLED_MESSAGE + " (was running)"
        run.status = "failed"
        run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
        session.add(item)
        session.add(run)
        session.commit()

        worker_tasks._finalize_s3_parent_run(session, run_id)
        session.refresh(run)
        assert run.status == "failed"
        assert run.error_message == worker_tasks._RUN_CANCELLED_MESSAGE


def test_execute_processed_item_respects_midflight_cancel(race_engine, monkeypatch):
    engine, item_id, run_id = race_engine
    monkeypatch.setattr(
        worker_tasks,
        "merge_project_and_org_llm_api_keys",
        lambda *_a, **_k: {},
    )

    original_execute = worker_tasks.execute_graph

    def _cancel_then_succeed(spec, **kwargs):
        with Session(engine) as session:
            item = session.get(AgateProcessedItem, item_id)
            run = session.get(AgateRun, run_id)
            assert item is not None and run is not None
            item.status = "failed"
            item.error_message = worker_tasks._RUN_CANCELLED_MESSAGE + " (was running)"
            run.status = "failed"
            run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
            session.add(item)
            session.add(run)
            session.commit()
        return original_execute(spec, **kwargs)

    with patch.object(worker_tasks, "execute_graph", side_effect=_cancel_then_succeed):
        worker_tasks.execute_processed_item(item_id)

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        run = session.get(AgateRun, run_id)
        assert item is not None and run is not None
        assert item.status == "failed"
        assert item.error_message and item.error_message.startswith(
            worker_tasks._RUN_CANCELLED_MESSAGE
        )
        assert run.status == "failed"
        assert run.error_message == worker_tasks._RUN_CANCELLED_MESSAGE
