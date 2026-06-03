"""S3 batch Celery tasks (eager broker, mocked S3 client).

``execute_s3_batch_setup`` queues a ``chord`` of ``execute_processed_item`` tasks;
eager mode runs the group and ``finalize_s3_parent_run`` inline.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine, select
from worker import tasks as worker_tasks


def _spec_with_s3() -> str:
    return json.dumps(
        {
            "name": "s3_flow",
            "nodes": [
                {
                    "id": "s3n",
                    "type": "S3Input",
                    "params": {"bucket": "my-bucket", "folder_path": "p", "max_files": 10},
                },
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "s3n", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buf.read()


class _FakeS3:
    def list_objects_v2(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "Contents": [
                {"Key": "p/bad.json"},
                {"Key": "p/good.json"},
            ],
            "IsTruncated": False,
        }

    def get_object(self, **_kwargs: Any) -> dict[str, Any]:
        key = str(_kwargs.get("Key") or "")
        if key.endswith("bad.json"):
            return {"Body": _FakeBody(b"not json")}
        if key.endswith("good.json"):
            return {"Body": _FakeBody(json.dumps({"text": "Batch line."}).encode())}
        raise AssertionError(key)


@pytest.fixture
def batch_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/s3batch.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None

    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker_tasks, "get_engine", lambda: engine)

    worker_tasks.celery_app.conf.task_always_eager = True
    worker_tasks.celery_app.conf.task_eager_propagates = True

    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-s3")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        ensure_default_stylebook_for_organization(session, oid)
        proj = BackfieldProject(organization_id=oid, name="P", slug="p-s3")
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        graph = AgateGraph(name="G", spec_json=_spec_with_s3(), project_id=pid)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

    yield engine, gid

    worker_tasks.celery_app.conf.task_always_eager = False
    worker_tasks.celery_app.conf.task_eager_propagates = False
    db_session._engine = None


def test_execute_s3_batch_setup_fanout_and_finalize(batch_engine, monkeypatch):
    engine, graph_id = batch_engine

    def _fake_s3() -> _FakeS3:
        return _FakeS3()

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", _fake_s3)

    def _stub_execute_graph(spec, node_runners=None, *, before_each_node=None, **kwargs):  # noqa: ARG001
        return {"s3_input": {"text": "stub"}}

    monkeypatch.setattr(worker_tasks, "execute_graph", _stub_execute_graph)

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "succeeded"
        graph = session.get(AgateGraph, graph_id)
        assert graph is not None
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
        ).all()
        assert len(items) == 2
        statuses = {row.status for row in items}
        assert "skipped" in statuses
        assert "succeeded" in statuses
        summary = json.loads(run.result_json or "{}")
        assert "items" in summary
        assert summary.get("s3_batch", {}).get("valid_executed") == 1
        assert summary.get("graph_spec_json") == graph.spec_json
