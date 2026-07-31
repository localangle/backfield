"""S3 ingestion ledger claim / skip / retry behavior."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from agate_runtime.s3_batch import S3ObjectListing, sha256_hex
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    AgateS3IngestionLedger,
    BackfieldOrganization,
    BackfieldProject,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine, select
from worker import tasks as worker_tasks
from worker.s3_ingestion_ledger import (
    S3_INGESTION_EXTERNAL_SOURCE,
    claim_ledger_revision,
    find_row_for_fingerprint,
    find_succeeded_matching_metadata,
    mark_ledger_succeeded,
)
from worker.substrate.content.article import _upsert_article


def _spec(source_id: str | None = None) -> str:
    params: dict[str, Any] = {"bucket": "my-bucket", "folder_path": "p", "max_files": 10}
    if source_id is not None:
        params["source_id"] = source_id
    return json.dumps(
        {
            "name": "s3_flow",
            "nodes": [
                {"id": "s3n", "type": "S3Input", "params": params},
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {
                    "source": "s3n",
                    "target": "out",
                    "sourceHandle": "text",
                    "targetHandle": "data",
                },
            ],
        }
    )


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buf.read()


class _MutableS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {
            "p/good.json": json.dumps({"text": "Batch line."}).encode(),
        }
        self.meta: dict[str, dict[str, Any]] = {
            "p/good.json": {
                "ETag": '"v1"',
                "Size": len(self.objects["p/good.json"]),
                "LastModified": datetime(2024, 1, 2, tzinfo=UTC),
            }
        }

    def list_objects_v2(self, **_kwargs: Any) -> dict[str, Any]:
        contents = []
        for key, meta in sorted(self.meta.items()):
            contents.append({"Key": key, **meta})
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs.get("Key") or "")
        body = self.objects[key]
        return {"Body": _FakeBody(body), "VersionId": self.meta[key].get("VersionId")}


@pytest.fixture
def ledger_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/s3ledger.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None

    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker_tasks, "get_engine", lambda: engine)

    worker_tasks.celery_app.conf.task_always_eager = True
    worker_tasks.celery_app.conf.task_eager_propagates = True

    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-ledger")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        ensure_default_stylebook_for_organization(session, oid)
        proj = BackfieldProject(organization_id=oid, name="P", slug="p-ledger")
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        graph = AgateGraph(name="G", spec_json=_spec("src-fixed"), project_id=pid)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

    yield engine, gid, pid

    worker_tasks.celery_app.conf.task_always_eager = False
    worker_tasks.celery_app.conf.task_eager_propagates = False
    db_session._engine = None


def _run_setup(engine, graph_id: str, s3: _MutableS3, monkeypatch) -> str:
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: s3)
    monkeypatch.setattr(
        worker_tasks,
        "execute_graph",
        lambda *args, **kwargs: {"s3_input": {"text": "stub"}},  # noqa: ARG005
    )
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)

    worker_tasks.execute_s3_batch_setup(run_id)
    return run_id


def test_first_scan_processes_second_unchanged_skips(ledger_engine, monkeypatch):
    engine, graph_id, _pid = ledger_engine
    s3 = _MutableS3()
    first = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        run = session.get(AgateRun, first)
        assert run is not None
        assert run.status == "succeeded"
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == first)
        ).all()
        assert len(items) == 1
        ledgers = session.exec(select(AgateS3IngestionLedger)).all()
        assert len(ledgers) == 1
        assert ledgers[0].status == "succeeded"

    second = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        run = session.get(AgateRun, second)
        assert run is not None
        assert run.status == "succeeded"
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == second)
        ).all()
        assert items == []
        summary = json.loads(run.result_json or "{}")
        assert summary["s3_batch"]["skipped_unchanged"] == 1
        assert summary["s3_batch"]["valid_executed"] == 0
        assert len(session.exec(select(AgateS3IngestionLedger)).all()) == 1


def test_ledger_identity_lookups_are_project_scoped(ledger_engine):
    engine, _graph_id, project_id = ledger_engine
    listing = S3ObjectListing(
        key="p/good.json",
        etag='"v1"',
        size_bytes=10,
        last_modified=datetime(2024, 1, 1),
    )
    with Session(engine) as session:
        project = session.get(BackfieldProject, project_id)
        assert project is not None
        other_project = BackfieldProject(
            organization_id=int(project.organization_id),
            name="Other",
            slug="other-ledger-project",
        )
        session.add(other_project)
        session.flush()
        other_project_id = int(other_project.id)  # type: ignore[arg-type]
        row = AgateS3IngestionLedger(
            project_id=project_id,
            source_id="shared-source",
            logical_item_id="my-bucket/p/good.json",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint="shared-fingerprint",
            etag="v1",
            size_bytes=10,
            last_modified=datetime(2024, 1, 1, tzinfo=UTC),
            status="succeeded",
            attempt_count=1,
        )
        session.add(row)
        session.commit()

        assert (
            find_succeeded_matching_metadata(
                session,
                project_id=project_id,
                source_id="shared-source",
                item_id="my-bucket/p/good.json",
                listing=listing,
            )
            is not None
        )
        assert (
            find_row_for_fingerprint(
                session,
                project_id=project_id,
                source_id="shared-source",
                item_id="my-bucket/p/good.json",
                content_fingerprint="shared-fingerprint",
            )
            is not None
        )
        assert (
            find_succeeded_matching_metadata(
                session,
                project_id=other_project_id,
                source_id="shared-source",
                item_id="my-bucket/p/good.json",
                listing=listing,
            )
            is None
        )
        assert (
            find_row_for_fingerprint(
                session,
                project_id=other_project_id,
                source_id="shared-source",
                item_id="my-bucket/p/good.json",
                content_fingerprint="shared-fingerprint",
            )
            is None
        )


def test_identical_revisions_are_processed_independently_by_project(ledger_engine, monkeypatch):
    engine, graph_id, project_id = ledger_engine
    s3 = _MutableS3()
    first_run_id = _run_setup(engine, graph_id, s3, monkeypatch)

    with Session(engine) as session:
        project = session.get(BackfieldProject, project_id)
        assert project is not None
        other_project = BackfieldProject(
            organization_id=int(project.organization_id),
            name="Other",
            slug="other-ledger-project",
        )
        session.add(other_project)
        session.flush()
        other_project_id = int(other_project.id)  # type: ignore[arg-type]
        other_graph = AgateGraph(
            name="Other graph",
            spec_json=_spec("src-fixed"),
            project_id=other_project_id,
        )
        session.add(other_graph)
        session.commit()
        session.refresh(other_graph)
        other_graph_id = str(other_graph.id)

    second_run_id = _run_setup(engine, other_graph_id, s3, monkeypatch)

    with Session(engine) as session:
        first_items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == first_run_id)
        ).all()
        second_items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == second_run_id)
        ).all()
        ledgers = session.exec(select(AgateS3IngestionLedger)).all()

        assert len(first_items) == 1
        assert len(second_items) == 1
        assert len(ledgers) == 2
        assert {row.project_id for row in ledgers} == {project_id, other_project_id}


def test_changed_contents_start_new_revision(ledger_engine, monkeypatch):
    engine, graph_id, _pid = ledger_engine
    s3 = _MutableS3()
    _run_setup(engine, graph_id, s3, monkeypatch)

    new_body = json.dumps({"text": "Changed body."}).encode()
    s3.objects["p/good.json"] = new_body
    s3.meta["p/good.json"] = {
        "ETag": '"v2"',
        "Size": len(new_body),
        "LastModified": datetime(2024, 2, 1, tzinfo=UTC),
    }
    second = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == second)
        ).all()
        assert len(items) == 1
        ledgers = session.exec(select(AgateS3IngestionLedger)).all()
        assert len(ledgers) == 2
        statuses = {row.status for row in ledgers}
        assert statuses == {"succeeded"}


def test_reprocess_unchanged_reclaims_succeeded(ledger_engine, monkeypatch):
    engine, graph_id, _pid = ledger_engine
    s3 = _MutableS3()
    _run_setup(engine, graph_id, s3, monkeypatch)

    with Session(engine) as session:
        graph = session.get(AgateGraph, graph_id)
        assert graph is not None
        spec = json.loads(graph.spec_json)
        spec["nodes"][0]["params"]["reprocess_unchanged"] = True
        graph.spec_json = json.dumps(spec)
        session.add(graph)
        session.commit()

    forced = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == forced)
        ).all()
        assert len(items) == 1
        assert items[0].status == "succeeded"
        ledger = session.exec(select(AgateS3IngestionLedger)).one()
        assert ledger.status == "succeeded"
        assert ledger.attempt_count >= 2


def test_identical_bytes_new_version_skipped(ledger_engine, monkeypatch):
    engine, graph_id, _pid = ledger_engine
    s3 = _MutableS3()
    _run_setup(engine, graph_id, s3, monkeypatch)

    # Same bytes, different VersionId / ETag forces GET; fingerprint still matches.
    s3.meta["p/good.json"] = {
        "ETag": '"different-etag"',
        "Size": len(s3.objects["p/good.json"]),
        "LastModified": datetime(2024, 3, 1, tzinfo=UTC),
        "VersionId": "ver-2",
    }
    second = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == second)
        ).all()
        assert items == []
        assert len(session.exec(select(AgateS3IngestionLedger)).all()) == 1


def test_failed_revision_retries_after_mark_failed(ledger_engine, monkeypatch):
    engine, graph_id, _pid = ledger_engine
    s3 = _MutableS3()

    def _failing_graph(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: s3)
    monkeypatch.setattr(worker_tasks, "execute_graph", _failing_graph)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)
    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        ledger = session.exec(select(AgateS3IngestionLedger)).one()
        assert ledger.status == "failed"

    retry = _run_setup(engine, graph_id, s3, monkeypatch)
    with Session(engine) as session:
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == retry)
        ).all()
        assert len(items) == 1
        assert items[0].status == "succeeded"
        ledger = session.exec(select(AgateS3IngestionLedger)).one()
        assert ledger.status == "succeeded"
        assert ledger.attempt_count >= 2


def test_expired_processing_lease_is_reclaimable(ledger_engine):
    engine, _graph_id, pid = ledger_engine
    listing = S3ObjectListing(
        key="p/good.json",
        etag='"v1"',
        size_bytes=10,
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )
    fingerprint = sha256_hex(b"same")
    with Session(engine) as session:
        first = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=fingerprint,
            listing=listing,
            version_id=None,
            flow_run_id="run-a",
            lease_duration=timedelta(seconds=1),
            now=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert first is not None
        session.commit()

        blocked = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=fingerprint,
            listing=listing,
            version_id=None,
            flow_run_id="run-b",
            lease_duration=timedelta(hours=1),
            now=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        assert blocked is None

        reclaimed = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=fingerprint,
            listing=listing,
            version_id=None,
            flow_run_id="run-c",
            lease_duration=timedelta(hours=1),
            now=datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC),
        )
        assert reclaimed is not None
        assert reclaimed.ledger_id == first.ledger_id
        assert reclaimed.claim_token != first.claim_token
        session.commit()


def test_concurrent_claim_only_one_wins(ledger_engine):
    engine, _graph_id, pid = ledger_engine
    listing = S3ObjectListing(
        key="p/good.json",
        etag='"v1"',
        size_bytes=10,
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )
    fingerprint = sha256_hex(b"concurrent")
    with Session(engine) as session:
        a = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=fingerprint,
            listing=listing,
            version_id=None,
            flow_run_id="run-a",
            lease_duration=timedelta(hours=1),
        )
        session.commit()
        assert a is not None

    with Session(engine) as session:
        b = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=fingerprint,
            listing=listing,
            version_id=None,
            flow_run_id="run-b",
            lease_duration=timedelta(hours=1),
        )
        assert b is None


def test_mark_succeeded_requires_claim_token(ledger_engine):
    engine, _graph_id, pid = ledger_engine
    listing = S3ObjectListing(key="p/good.json", etag='"e"', size_bytes=1)
    with Session(engine) as session:
        claim = claim_ledger_revision(
            session,
            project_id=pid,
            source_id="src-fixed",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint=sha256_hex(b"x"),
            listing=listing,
            version_id=None,
            flow_run_id="run-a",
            lease_duration=timedelta(hours=1),
        )
        assert claim is not None
        session.commit()
        assert not mark_ledger_succeeded(
            session,
            ledger_id=claim.ledger_id,
            claim_token=str(uuid4()),
            processed_item_id=1,
        )
        assert mark_ledger_succeeded(
            session,
            ledger_id=claim.ledger_id,
            claim_token=claim.claim_token,
            processed_item_id=1,
        )
        session.commit()
        row = session.get(AgateS3IngestionLedger, claim.ledger_id)
        assert row is not None
        assert row.status == "succeeded"


def test_article_upsert_prefers_ledger_identity(ledger_engine):
    engine, graph_id, pid = ledger_engine
    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        ledger = AgateS3IngestionLedger(
            project_id=pid,
            source_id="src-fixed",
            logical_item_id="my-bucket/p/good.json",
            bucket="my-bucket",
            key="p/good.json",
            content_fingerprint="abc",
            status="processing",
            claim_token=str(uuid4()),
            attempt_count=1,
            flow_run_id=str(run.id),
        )
        session.add(ledger)
        session.commit()
        session.refresh(ledger)
        item = AgateProcessedItem(
            run_id=str(run.id),
            source_file="p/good.json",
            input_json=json.dumps({"text": "hello"}),
            status="running",
            ingestion_ledger_id=str(ledger.id),
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        article = _upsert_article(
            session,
            project_id=pid,
            consolidated={
                "text": "hello",
                "publication": "OtherPub",
                "entry_id": "doc-1",
                "headline": "H",
            },
            run_id=str(run.id),
            processed_item_id=int(item.id),
        )
        session.commit()
        assert article.external_source == S3_INGESTION_EXTERNAL_SOURCE
        assert article.external_id == str(ledger.id)

        again = _upsert_article(
            session,
            project_id=pid,
            consolidated={
                "text": "hello changed",
                "publication": "OtherPub",
                "entry_id": "doc-1",
                "headline": "H2",
            },
            run_id=str(run.id),
            processed_item_id=int(item.id),
        )
        session.commit()
        assert int(again.id) == int(article.id)
        assert again.headline == "H2"
