"""Worker process startup helpers (build metadata logging)."""

from __future__ import annotations

import logging
import os

from backfield_auth.service_health import read_build_info
from backfield_auth.structured_logging import configure_structured_logging, log_event

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = "16"


def read_worker_build_info() -> dict[str, str]:
    """Read worker build metadata from environment with safe defaults."""
    info = read_build_info("worker")
    concurrency = os.environ.get("CELERY_WORKER_CONCURRENCY", _DEFAULT_CONCURRENCY).strip()
    return {
        "service": info.service,
        "version": info.version,
        "git_sha": info.git_sha,
        "build_time": info.build_time,
        "concurrency": concurrency or _DEFAULT_CONCURRENCY,
    }


def log_worker_startup() -> None:
    configure_structured_logging("worker")
    log_event(logger, "worker_startup", **read_worker_build_info())
