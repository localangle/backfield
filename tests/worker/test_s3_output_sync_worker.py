"""S3 Output re-sync Celery task (mocked S3 client, sqlite engine)."""

from __future__ import annotations

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
from sqlmodel import Session, SQLModel, create_engine
from worker import tasks as worker_tasks


def _spec_with_s3_output() -> str:
    return json.dumps(
        {
            "name": "s3_out_flow",
            "nodes": [
                {
                    "id": "s3n",
                    "type": "S3Input",
                    "params": {"bucket": "in-bucket", "folder_path": "in", "max_files": 10},
                },
                {
                    "id": "s3out",
                    "type": "S3Output",
                    "params": {"bucket": "out-bucket", "output_path": "out", "public_read": True},
                },
            ],
            "edges": [
                {
                    "source": "s3n",
                    "target": "s3out",
                    "sourceHandle": "text",
                    "targetHandle": "data",
                },
            ],
        }
    )


class _FakeS3:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)


class _FailingS3:
    def put_object(self, **_kwargs: Any) -> None:
        raise RuntimeError("access denied")


@pytest.fixture
def sync_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/s3sync.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None

    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker_tasks, "get_engine", lambda: engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-s3sync")
        session.add(org)
        session.commit()
        session.refresh(org)
        proj = BackfieldProject(organization_id=int(org.id), name="P", slug="p-s3sync")  # type: ignore[arg-type]
        session.add(proj)
        session.commit()
        session.refresh(proj)
        graph = AgateGraph(
            name="G",
            spec_json=_spec_with_s3_output(),
            project_id=int(proj.id),  # type: ignore[arg-type]
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

    yield engine, gid

    db_session._engine = None


def _insert_item(
    session: Session,
    graph_id: str,
    *,
    result_json: str,
    reviewed_output_json: str | None = None,
) -> int:
    run = AgateRun(graph_id=graph_id, status="succeeded")
    session.add(run)
    session.commit()
    session.refresh(run)
    item = AgateProcessedItem(
        run_id=run.id,
        source_file="in/2026-06-01/story.json",
        input_json="{}",
        status="succeeded",
        result_json=result_json,
        reviewed_output_json=reviewed_output_json,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return int(item.id)  # type: ignore[arg-type]


def _result_json(text: str = "Original text.") -> str:
    return json.dumps(
        {
            "s3_input": {"text": text, "source_file": "in/2026-06-01/story.json"},
            "s3_output": {
                "consolidated": {"text": text},
                "s3_bucket": "out-bucket",
                "s3_key": "out/2026-06-01/story-output.json",
            },
        }
    )


def test_sync_uploads_reviewed_output_when_present(sync_engine, monkeypatch) -> None:
    engine, graph_id = sync_engine
    fake = _FakeS3()
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: fake)

    reviewed = json.loads(_result_json())
    reviewed["s3_output"]["consolidated"]["text"] = "Reviewed text."
    with Session(engine) as session:
        item_id = _insert_item(
            session,
            graph_id,
            result_json=_result_json(),
            reviewed_output_json=json.dumps(reviewed),
        )

    worker_tasks.sync_processed_item_s3_output(item_id)

    assert len(fake.put_calls) == 1
    call = fake.put_calls[0]
    assert call["Bucket"] == "out-bucket"
    assert call["Key"] == "out/2026-06-01/story-output.json"
    assert call["ACL"] == "public-read"
    body = json.loads(call["Body"].decode("utf-8"))
    assert body["text"] == "Reviewed text."

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        output = json.loads(item.result_json or "{}")
        assert output["s3_output"]["s3_synced_at"]
        assert "s3_sync_error" not in output["s3_output"]
        reviewed_doc = json.loads(item.reviewed_output_json or "{}")
        assert reviewed_doc["s3_output"]["s3_synced_at"]


def test_sync_uploads_original_output_without_review(sync_engine, monkeypatch) -> None:
    engine, graph_id = sync_engine
    fake = _FakeS3()
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: fake)

    with Session(engine) as session:
        item_id = _insert_item(session, graph_id, result_json=_result_json())

    worker_tasks.sync_processed_item_s3_output(item_id)

    assert len(fake.put_calls) == 1
    body = json.loads(fake.put_calls[0]["Body"].decode("utf-8"))
    assert body["text"] == "Original text."


def test_sync_skips_item_without_s3_output_payload(sync_engine, monkeypatch) -> None:
    engine, graph_id = sync_engine
    fake = _FakeS3()
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: fake)

    with Session(engine) as session:
        item_id = _insert_item(
            session,
            graph_id,
            result_json=json.dumps({"json_output": {"consolidated": {"text": "Hi"}}}),
        )

    worker_tasks.sync_processed_item_s3_output(item_id)
    assert fake.put_calls == []


def test_sync_records_error_when_upload_fails(sync_engine, monkeypatch) -> None:
    engine, graph_id = sync_engine
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: _FailingS3())

    with Session(engine) as session:
        item_id = _insert_item(session, graph_id, result_json=_result_json())

    worker_tasks.sync_processed_item_s3_output(item_id)

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        output = json.loads(item.result_json or "{}")
        assert "access denied" in output["s3_output"]["s3_sync_error"]
        assert "s3_synced_at" not in output["s3_output"]
