"""Worker startup metadata logging."""

from __future__ import annotations

import json
import logging

from worker.startup import log_worker_startup, read_worker_build_info


def test_read_worker_build_info_uses_env_with_defaults(monkeypatch) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)
    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)

    assert read_worker_build_info() == {
        "service": "worker",
        "version": "0.1.0",
        "git_sha": "unknown",
        "build_time": "unknown",
        "concurrency": "16",
    }


def test_read_worker_build_info_reads_baked_metadata(monkeypatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v9.8.7")
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    monkeypatch.setenv("BUILD_TIME", "2026-06-26T12:00:00Z")
    monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "7")

    assert read_worker_build_info() == {
        "service": "worker",
        "version": "v9.8.7",
        "git_sha": "deadbeef",
        "build_time": "2026-06-26T12:00:00Z",
        "concurrency": "7",
    }


def test_log_worker_startup_emits_json(caplog) -> None:
    caplog.set_level(logging.INFO, logger="worker.startup")

    log_worker_startup()

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "worker_startup"
    assert payload["service"] == "worker"
    assert "version" in payload
    assert "git_sha" in payload
    assert "build_time" in payload
    assert "concurrency" in payload
