"""Structural checks for runtime contracts and schema conventions."""

from __future__ import annotations

from api.routers import runs
from backfield_db import AgateGraph, AgateProject, AgateProjectSecret, AgateRun, AgateTemplate
from worker import tasks as worker_tasks


def test_agate_tables_use_app_prefix():
    table_names = {
        AgateProject.__tablename__,
        AgateGraph.__tablename__,
        AgateRun.__tablename__,
        AgateTemplate.__tablename__,
        AgateProjectSecret.__tablename__,
    }
    assert all(name.startswith("agate_") for name in table_names)


def test_expected_indexes_exist():
    project_indexes = {index.name for index in AgateProject.__table__.indexes}
    run_indexes = {index.name for index in AgateRun.__table__.indexes}
    secret_indexes = {index.name for index in AgateProjectSecret.__table__.indexes}

    assert "ix_agate_project_slug" in project_indexes
    assert "ix_agate_run_graph_id" in run_indexes
    assert "ix_agate_project_secret_project_id" in secret_indexes


def test_queue_and_task_contracts_match():
    assert runs.celery_app.main == "agate_worker"
    assert worker_tasks.celery_app.main == "agate_worker"
    assert worker_tasks.execute_agate_run.name == "worker.tasks.execute_agate_run"
