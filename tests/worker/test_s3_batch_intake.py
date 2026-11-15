"""Chunked S3 intake: pure helpers and streaming setup with a fake Redis (no real runs)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from agate_runtime.s3_batch import S3ObjectListing
from backfield_db import AgateProcessedItem, AgateRun
from sqlmodel import Session, select
from worker import s3_batch_intake
from worker import tasks as worker_tasks

from tests.worker.test_s3_batch_worker import _FakeBody, batch_engine  # noqa: F401


def _listing(key: str) -> S3ObjectListing:
    return S3ObjectListing(
        key=key,
        etag='"e"',
        size_bytes=10,
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_chunked_splits_in_order() -> None:
    assert [list(c) for c in s3_batch_intake.chunked([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]
    assert list(s3_batch_intake.chunked([], 3)) == []


def test_intake_settings_read_env(monkeypatch) -> None:
    monkeypatch.setenv("S3_BATCH_INTAKE_CHUNK_SIZE", "7")
    monkeypatch.setenv("S3_BATCH_FETCH_WORKERS", "bad")
    monkeypatch.setenv("S3_BATCH_RAMP_SECONDS", "0")
    assert s3_batch_intake.intake_chunk_size() == 7
    assert s3_batch_intake.fetch_worker_count() == 16
    assert s3_batch_intake.ramp_seconds() == 0.0


def test_fetch_objects_reads_in_parallel_and_reports_failures() -> None:
    class _S3:
        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            if kwargs["Key"] == "bad":
                raise RuntimeError("boom")
            return {"Body": _FakeBody(kwargs["Key"].encode()), "VersionId": "v1"}

    listings = [_listing("a"), _listing("bad"), _listing("c")]
    fetched = s3_batch_intake.fetch_objects(_S3(), bucket="b", listings=listings, workers=4)
    assert fetched["a"].raw_bytes == b"a"
    assert fetched["a"].version_id == "v1"
    assert fetched["bad"].raw_bytes is None
    assert fetched["bad"].error is not None
    assert fetched["c"].raw_bytes == b"c"


def test_ramp_spreads_first_window_then_starts_refills_immediately() -> None:
    ramp = s3_batch_intake.IntakeRamp(window=4, ramp_s=40)
    first_window = [ramp.next_countdown_s() for _ in range(4)]
    assert first_window[0] == 0
    assert first_window == sorted(first_window)
    assert first_window[-1] >= 28
    assert ramp.next_countdown_s() == 0


def test_ramp_disabled_starts_everything_at_once() -> None:
    ramp = s3_batch_intake.IntakeRamp(window=4, ramp_s=0)
    assert [ramp.next_countdown_s() for _ in range(6)] == [0] * 6


class _FakeRedis:
    """The few list commands the pending-id helpers use."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def pipeline(self) -> _FakeRedis:
        return self

    def execute(self) -> None:
        return None

    def delete(self, key: str) -> None:
        self.lists.pop(key, None)

    def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    def expire(self, key: str, _seconds: int) -> None:
        return None

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def lpop(self, key: str) -> str | None:
        items = self.lists.get(key, [])
        return items.pop(0) if items else None


class _ManyObjectsS3:
    def __init__(self, count: int) -> None:
        self.count = count

    def list_objects_v2(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "Contents": [
                {
                    "Key": f"p/{index:03d}.json",
                    "ETag": f'"etag-{index}"',
                    "Size": 32,
                    "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                }
                for index in range(self.count)
            ],
            "IsTruncated": False,
        }

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        text = f"Article {kwargs['Key']}"
        return {"Body": _FakeBody(json.dumps({"text": text}).encode())}


@pytest.fixture
def streaming_setup(batch_engine, monkeypatch):  # noqa: F811
    engine, graph_id = batch_engine
    worker_tasks.celery_app.conf.task_always_eager = False
    redis = _FakeRedis()
    queued: list[tuple[int, int]] = []

    class _RecordingTask:
        @staticmethod
        def apply_async(*, args: list[int], queue: str, countdown: int = 0) -> None:  # noqa: ARG004
            queued.append((args[0], countdown))

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setenv("S3_BATCH_INTAKE_CHUNK_SIZE", "4")
    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "6")
    monkeypatch.setenv("S3_BATCH_RAMP_SECONDS", "60")
    monkeypatch.setattr(worker_tasks, "_redis_client_or_none", lambda: redis)
    monkeypatch.setattr(worker_tasks, "execute_processed_item", _RecordingTask)
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: _ManyObjectsS3(10))

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)
    return engine, run_id, redis, queued


def test_large_prefix_streams_chunks_and_fills_the_window(streaming_setup) -> None:
    engine, run_id, redis, queued = streaming_setup

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "running"
        batch = json.loads(run.result_json or "{}")["s3_batch"]
        assert batch["intake_complete"] is True
        assert batch["valid_executed"] == 10
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
        ).all()
        assert len(items) == 10
    # Window of 6 is filled; the other 4 wait in Redis for completions to refill.
    assert len(queued) == 6
    assert len(redis.lists[worker_tasks._batch_pending_redis_key(run_id)]) == 4
    # The ramp staggers the first window rather than starting it all at once.
    countdowns = [countdown for _item_id, countdown in queued]
    assert countdowns[0] == 0
    assert max(countdowns) > 0


def test_finalization_waits_for_intake_to_finish(streaming_setup) -> None:
    engine, run_id, _redis, _queued = streaming_setup
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        run.status = "running"
        run.result_json = json.dumps({"s3_batch": {"intake_complete": False}})
        session.add(run)
        session.add(
            AgateProcessedItem(
                run_id=run_id, source_file="a.json", input_json="{}", status="succeeded"
            )
        )
        session.commit()

        worker_tasks._finalize_s3_parent_run(session, run_id)
        session.expire_all()
        assert session.get(AgateRun, run_id).status == "running"  # type: ignore[union-attr]

        run = session.get(AgateRun, run_id)
        run.result_json = json.dumps({"s3_batch": {"intake_complete": True}})  # type: ignore[union-attr]
        session.add(run)
        session.commit()

        worker_tasks._finalize_s3_parent_run(session, run_id)
        session.expire_all()
        assert session.get(AgateRun, run_id).status == "succeeded"  # type: ignore[union-attr]


def test_cancel_during_streaming_intake_stops_loading(streaming_setup, monkeypatch) -> None:
    engine, run_id, _redis, queued = streaming_setup

    class _CancelAfterFirstChunk(_ManyObjectsS3):
        reads = 0

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            type(self).reads += 1
            if type(self).reads == 5:  # first read of the second chunk
                with Session(engine) as cancel_session:
                    run = cancel_session.get(AgateRun, run_id)
                    assert run is not None
                    run.status = "failed"
                    run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
                    cancel_session.add(run)
                    cancel_session.commit()
            return super().get_object(**kwargs)

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: _CancelAfterFirstChunk(10))
    # Sequential reads make the cancel point deterministic.
    monkeypatch.setenv("S3_BATCH_FETCH_WORKERS", "1")

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "failed"
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
        ).all()
        assert len(items) == 4  # only the chunk committed before the cancel
    assert len(queued) == 4


def test_small_prefix_keeps_single_pass_without_completion_flag(
    streaming_setup, monkeypatch
) -> None:
    engine, run_id, redis, queued = streaming_setup
    monkeypatch.setenv("S3_BATCH_INTAKE_CHUNK_SIZE", "50")
    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "100")
    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", lambda: _ManyObjectsS3(3))
    monkeypatch.setattr(
        worker_tasks,
        "queue_execute_processed_item_chord",
        lambda _run_id, ids: queued.extend((item_id, 0) for item_id in ids),
    )

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        batch = json.loads(run.result_json or "{}")["s3_batch"]
        assert "intake_complete" not in batch
        assert batch["valid_executed"] == 3
    assert len(queued) == 3
    assert redis.lists == {}
