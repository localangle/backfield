#!/usr/bin/env python3
"""Deterministic S3 batch smoke using the worker task implementation directly."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from _helpers import log
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
            "name": "smoke_s3_batch",
            "nodes": [
                {
                    "id": "s3",
                    "type": "S3Input",
                    "params": {"bucket": "smoke-bucket", "folder_path": "seed", "max_files": 10},
                },
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {
                    "source": "s3",
                    "target": "out",
                    "sourceHandle": "text",
                    "targetHandle": "data",
                }
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
                {"Key": "seed/bad.json"},
                {"Key": "seed/good.json"},
            ],
            "IsTruncated": False,
        }

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs.get("Key") or "")
        if key.endswith("bad.json"):
            return {"Body": _FakeBody(b"not json")}
        if key.endswith("good.json"):
            return {"Body": _FakeBody(json.dumps({"text": "Batch smoke line."}).encode())}
        raise RuntimeError(f"Unexpected S3 key: {key}")


def _stub_execute_graph(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"s3_input": {"text": "stub"}}


def main() -> int:
    temp_dir = tempfile.TemporaryDirectory(prefix="backfield-smoke-s3-")
    url = f"sqlite:///{Path(temp_dir.name) / 'smoke_s3_batch.db'}"

    import backfield_db.session as db_session

    original_engine = db_session._engine
    original_get_engine = worker_tasks.get_engine
    original_s3_client = worker_tasks._s3_client_from_env
    original_execute_graph = worker_tasks.execute_graph
    original_always_eager = worker_tasks.celery_app.conf.task_always_eager
    original_eager_propagates = worker_tasks.celery_app.conf.task_eager_propagates

    try:
        db_session._engine = None
        os.environ["BACKFIELD_DATABASE_URL"] = url
        engine = create_engine(url, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)

        worker_tasks.get_engine = lambda: engine
        worker_tasks._s3_client_from_env = lambda: _FakeS3()
        worker_tasks.execute_graph = _stub_execute_graph
        worker_tasks.celery_app.conf.task_always_eager = True
        worker_tasks.celery_app.conf.task_eager_propagates = True
        os.environ["AWS_ACCESS_KEY_ID"] = "smoke-ak"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "smoke-sk"

        with Session(engine) as session:
            org = BackfieldOrganization(name="Smoke Org", slug="smoke-org")
            session.add(org)
            session.commit()
            session.refresh(org)
            if org.id is None:
                raise RuntimeError("Organization id missing")

            ensure_default_stylebook_for_organization(session, int(org.id))
            project = BackfieldProject(
                organization_id=int(org.id),
                name="Smoke Project",
                slug="smoke-proj",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            if project.id is None:
                raise RuntimeError("Project id missing")

            graph = AgateGraph(
                name="Smoke S3 Batch",
                spec_json=_spec_with_s3(),
                project_id=int(project.id),
            )
            session.add(graph)
            session.commit()
            session.refresh(graph)

            run = AgateRun(graph_id=graph.id, status="pending")
            session.add(run)
            session.commit()
            session.refresh(run)

        worker_tasks.execute_s3_batch_setup(run.id)

        with Session(engine) as session:
            run_row = session.get(AgateRun, run.id)
            if run_row is None:
                raise RuntimeError("S3 smoke run row missing")
            if run_row.status != "succeeded":
                raise RuntimeError(
                    "Expected succeeded parent run, "
                    f"got {run_row.status!r}: {run_row.error_message!r}"
                )

            items = list(
                session.exec(
                    select(AgateProcessedItem).where(AgateProcessedItem.run_id == run.id)
                ).all()
            )
            if len(items) != 2:
                raise RuntimeError(f"Expected two processed items, got {len(items)}")
            statuses = {row.status for row in items}
            if statuses != {"skipped", "succeeded"}:
                raise RuntimeError(f"Unexpected processed item statuses: {sorted(statuses)!r}")

            summary = json.loads(run_row.result_json or "{}")
            batch = summary.get("s3_batch")
            if not isinstance(batch, dict) or int(batch.get("valid_executed", -1)) != 1:
                raise RuntimeError(f"Unexpected s3_batch summary: {summary!r}")
            items_payload = summary.get("items")
            if not isinstance(items_payload, list) or len(items_payload) != 2:
                raise RuntimeError(f"Expected batch summary items list: {summary!r}")

        log("Smoke s3 batch passed.")
        log(f"Run: {run.id}")
        return 0
    finally:
        worker_tasks.get_engine = original_get_engine
        worker_tasks._s3_client_from_env = original_s3_client
        worker_tasks.execute_graph = original_execute_graph
        worker_tasks.celery_app.conf.task_always_eager = original_always_eager
        worker_tasks.celery_app.conf.task_eager_propagates = original_eager_propagates
        db_session._engine = original_engine
        temp_dir.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke failure: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
