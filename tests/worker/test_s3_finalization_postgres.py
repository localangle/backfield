"""PostgreSQL locking coverage for competing parent-run finalizers."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlalchemy import delete, event
from sqlmodel import Session, create_engine
from worker import tasks as worker_tasks

_DATABASE_URL = os.getenv("BACKFIELD_DATABASE_URL_DIRECT", "")


@pytest.mark.skipif(
    not _DATABASE_URL.startswith("postgresql"),
    reason="requires BACKFIELD_DATABASE_URL_DIRECT for PostgreSQL",
)
def test_competing_finalizers_mutate_parent_once(monkeypatch) -> None:
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    barrier = Barrier(2)
    mutation_lock = Lock()
    parent_updates: list[str] = []
    original_parent_status = worker_tasks._parent_run_status

    def synchronized_parent_status(session: Session, run_id: str) -> str | None:
        status = original_parent_status(session, run_id)
        barrier.wait(timeout=10)
        return status

    def capture_parent_updates(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        normalized = str(statement).lower().strip()
        if normalized.startswith("update agate_run "):
            with mutation_lock:
                parent_updates.append(normalized)

    monkeypatch.setattr(worker_tasks, "_parent_run_status", synchronized_parent_status)
    event.listen(engine, "before_cursor_execute", capture_parent_updates)

    organization_id: int | None = None
    project_id: int | None = None
    graph_id: str | None = None
    run_id: str | None = None
    try:
        with Session(engine) as session:
            organization = BackfieldOrganization(
                name=f"Finalizer race {suffix}",
                slug=f"finalizer-race-{suffix}",
            )
            session.add(organization)
            session.commit()
            session.refresh(organization)
            organization_id = int(organization.id)

            project = BackfieldProject(
                organization_id=organization_id,
                name=f"Finalizer race {suffix}",
                slug=f"finalizer-race-{suffix}",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = int(project.id)

            graph = AgateGraph(
                project_id=project_id,
                name="Finalizer race",
                spec_json=json.dumps({"name": "race", "nodes": [], "edges": []}),
            )
            session.add(graph)
            session.commit()
            session.refresh(graph)
            graph_id = str(graph.id)

            run = AgateRun(
                graph_id=graph_id,
                status="running",
                result_json=json.dumps({"s3_batch": {"valid_executed": 2}}),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = str(run.id)
            session.add(
                AgateProcessedItem(
                    run_id=run_id,
                    source_file="batch/1.json",
                    status="succeeded",
                )
            )
            session.add(
                AgateProcessedItem(
                    run_id=run_id,
                    source_file="batch/2.json",
                    status="skipped",
                )
            )
            session.commit()

        def finalize() -> None:
            assert run_id is not None
            with Session(engine) as session:
                worker_tasks._finalize_s3_parent_run(session, run_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(finalize) for _ in range(2)]
            for future in futures:
                future.result(timeout=20)

        with Session(engine) as session:
            run = session.get(AgateRun, run_id)
            assert run is not None
            assert run.status == "succeeded"
            payload = json.loads(run.result_json or "{}")
            assert payload["s3_batch"] == {"valid_executed": 2}
            assert len(payload["items"]) == 2
        assert len(parent_updates) == 1
    finally:
        event.remove(engine, "before_cursor_execute", capture_parent_updates)
        with Session(engine) as session:
            if run_id is not None:
                session.execute(
                    delete(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
                )
                session.execute(delete(AgateRun).where(AgateRun.id == run_id))
            if graph_id is not None:
                session.execute(delete(AgateGraph).where(AgateGraph.id == graph_id))
            if project_id is not None:
                session.execute(
                    delete(BackfieldProject).where(BackfieldProject.id == project_id)
                )
            if organization_id is not None:
                session.execute(
                    delete(BackfieldOrganization).where(
                        BackfieldOrganization.id == organization_id
                    )
                )
            session.commit()
        engine.dispose()
