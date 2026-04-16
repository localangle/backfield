"""Celery tasks."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import UTC, datetime

from backfield_core import GraphSpec, execute_graph
from backfield_core.nodes import NODE_RUNNERS
from backfield_db import AgateGraph, AgateRun, BackfieldProjectSecret
from backfield_db.crypto import decrypt_secret, fernet_from_env
from backfield_db.session import get_engine
from celery import Celery
from sqlmodel import Session, select

from worker.nodes.db_output import run_db_output

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


@contextmanager
def _env_overlay(updates: dict[str, str]):
    keys = list(updates.keys())
    previous: dict[str, str | None] = {k: os.environ.get(k) for k in keys}
    try:
        for k, v in updates.items():
            os.environ[k] = v
        yield
    finally:
        for k in keys:
            prev = previous.get(k)
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def _project_env_map(session: Session, project_id: int) -> dict[str, str]:
    f = fernet_from_env()
    if f is None:
        return {}
    rows = session.exec(
        select(BackfieldProjectSecret).where(BackfieldProjectSecret.project_id == project_id)
    ).all()
    out: dict[str, str] = {}
    for r in rows:
        try:
            out[r.key] = decrypt_secret(r.value_encrypted)
        except Exception:
            continue
    return out


@contextmanager
def _run_execution_env(*, project_id: int, graph_id: str, run_id: str):
    updates = {
        "BACKFIELD_PROJECT_ID": str(project_id),
        "BACKFIELD_GRAPH_ID": str(graph_id),
        "BACKFIELD_RUN_ID": str(run_id),
    }
    with _env_overlay(updates):
        yield


@celery_app.task(name="worker.tasks.execute_agate_run")
def execute_agate_run(run_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        if not run:
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            run.status = "failed"
            run.error_message = "Graph not found"
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()
            return

        run.status = "running"
        session.add(run)
        session.commit()

        try:
            spec = GraphSpec.model_validate_json(graph.spec_json)
            overlay = _project_env_map(session, graph.project_id)
            node_runners = dict(NODE_RUNNERS)
            node_runners["DBOutput"] = run_db_output
            with _env_overlay(overlay), _run_execution_env(
                project_id=graph.project_id,
                graph_id=graph.id,
                run_id=run.id,
            ):
                outputs = execute_graph(spec, node_runners=node_runners)
            run.status = "succeeded"
            run.result_json = json.dumps(outputs)
            run.error_message = None
        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.result_json = None
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()
