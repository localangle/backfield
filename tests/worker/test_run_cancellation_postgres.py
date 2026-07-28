"""PostgreSQL coverage for cancellation racing with worker completion."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
from api.routers import runs as run_routes
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlalchemy import delete
from sqlmodel import Session, create_engine, select
from worker import tasks as worker_tasks

_DATABASE_URL = os.getenv("BACKFIELD_DATABASE_URL_DIRECT", "")


@pytest.mark.skipif(
    not _DATABASE_URL.startswith("postgresql"),
    reason="requires BACKFIELD_DATABASE_URL_DIRECT for PostgreSQL",
)
def test_cancel_wins_before_worker_stores_completion() -> None:
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    cancellation_applied = Event()
    allow_cancellation_commit = Event()

    organization_id: int | None = None
    project_id: int | None = None
    graph_id: str | None = None
    run_id: str | None = None
    item_id: int | None = None
    claimed_at: datetime | None = None
    try:
        with Session(engine) as session:
            organization = BackfieldOrganization(
                name=f"Cancellation race {suffix}",
                slug=f"cancellation-race-{suffix}",
            )
            session.add(organization)
            session.commit()
            session.refresh(organization)
            organization_id = int(organization.id)
            project = BackfieldProject(
                organization_id=organization_id,
                name=f"Cancellation race {suffix}",
                slug=f"cancellation-race-{suffix}",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = int(project.id)
            graph = AgateGraph(
                project_id=project_id,
                name="Cancellation race",
                spec_json=json.dumps({"name": "race", "nodes": [], "edges": []}),
            )
            session.add(graph)
            session.commit()
            session.refresh(graph)
            graph_id = str(graph.id)
            run = AgateRun(graph_id=graph_id, status="running")
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = str(run.id)
            item = AgateProcessedItem(
                run_id=run_id,
                source_file="batch/1.json",
                status="running",
                started_at=datetime.now(UTC),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            item_id = int(item.id)
            claimed_at = item.started_at

        def cancel() -> None:
            assert run_id is not None
            with Session(engine) as session:
                run = session.exec(
                    select(AgateRun).where(AgateRun.id == run_id).with_for_update()
                ).one()
                now = datetime.now(UTC)
                run.status = "failed"
                run.error_message = run_routes._RUN_CANCELLED_MESSAGE
                run.updated_at = now
                session.add(run)
                run_routes._cancel_processed_items(session, run_id, now=now)
                session.flush()
                cancellation_applied.set()
                assert allow_cancellation_commit.wait(timeout=10)
                session.commit()

        def store_worker_completion() -> bool:
            assert run_id is not None
            assert item_id is not None
            assert claimed_at is not None
            with Session(engine) as session:
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
                if stored:
                    session.commit()
                else:
                    session.rollback()
                return stored

        with ThreadPoolExecutor(max_workers=2) as executor:
            cancel_future = executor.submit(cancel)
            assert cancellation_applied.wait(timeout=10)
            worker_future = executor.submit(store_worker_completion)
            time.sleep(0.2)
            assert not worker_future.done()
            allow_cancellation_commit.set()
            cancel_future.result(timeout=10)
            assert worker_future.result(timeout=10) is False

        with Session(engine) as session:
            run = session.get(AgateRun, run_id)
            item = session.get(AgateProcessedItem, item_id)
            assert run is not None
            assert item is not None
            assert run.status == "failed"
            assert run.error_message == run_routes._RUN_CANCELLED_MESSAGE
            assert item.status == "failed"
            assert item.error_message == run_routes._RUN_CANCELLED_MESSAGE + " (was running)"
            assert item.result_json is None
    finally:
        allow_cancellation_commit.set()
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
