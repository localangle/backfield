"""Fixtures shared by the worker tests."""

from __future__ import annotations

import pytest
from backfield_db import (
    AgateGraph,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine
from worker import tasks as worker_tasks

from tests.worker.s3_batch_helpers import spec_with_s3


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
        stylebook = ensure_default_stylebook_for_organization(session, oid)
        workspace = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=int(stylebook.id),
            name="Workspace",
            slug="s3-worker",
        )
        session.add(workspace)
        session.flush()
        proj = BackfieldProject(
            organization_id=oid,
            workspace_id=int(workspace.id),
            stylebook_id=int(stylebook.id),
            name="P",
            slug="p-s3",
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        graph = AgateGraph(name="G", spec_json=spec_with_s3(), project_id=pid)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

    yield engine, gid

    worker_tasks.celery_app.conf.task_always_eager = False
    worker_tasks.celery_app.conf.task_eager_propagates = False
    db_session._engine = None
