"""Worker startup metadata logging."""

from __future__ import annotations

import gc
import logging
from unittest.mock import patch

from worker.startup import (
    log_worker_startup,
    prepare_worker_parent_for_fork,
    read_worker_build_info,
    warm_worker_process,
)


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


def test_log_worker_startup_emits_json(caplog, monkeypatch) -> None:
    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)
    caplog.set_level(logging.INFO, logger="worker.startup")

    log_worker_startup()

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.event == "worker_startup"
    assert record.service == "worker"
    assert record.version == "0.1.0"
    assert record.git_sha == "unknown"
    assert record.build_time == "unknown"
    assert record.concurrency == "16"


def test_warm_worker_process_warms_imports_and_freezes_heap() -> None:
    with (
        patch("backfield_ai.litellm_warmup.warm_litellm_imports") as warm,
        patch("worker.startup.gc.freeze") as freeze,
    ):
        warm_worker_process()
    warm.assert_called_once()
    freeze.assert_called_once()


def test_prepare_worker_parent_for_fork_warms_collects_and_freezes() -> None:
    with (
        patch("backfield_ai.litellm_warmup.warm_litellm_imports") as warm,
        patch("worker.startup.gc.collect") as collect,
        patch("worker.startup.gc.freeze") as freeze,
    ):
        prepare_worker_parent_for_fork()
    warm.assert_called_once()
    collect.assert_called_once()
    freeze.assert_called_once()


def test_celery_signal_hooks_survive_garbage_collection() -> None:
    """Hooks must connect with ``weak=False``; Celery signals drop weakly-held closures."""
    import worker.tasks  # noqa: F401  (registers signal hooks on import)
    from celery.signals import worker_init, worker_process_init

    gc.collect()
    with (
        patch("backfield_ai.litellm_warmup.warm_litellm_imports") as warm,
        patch("worker.startup.gc.collect"),
        patch("worker.startup.gc.freeze") as freeze,
    ):
        worker_init.send(sender=None)
        worker_process_init.send(sender=None)
    assert warm.call_count == 2
    assert freeze.call_count == 2
