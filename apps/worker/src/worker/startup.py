"""Worker process startup helpers (build metadata logging)."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = "16"


def read_worker_build_info() -> dict[str, str]:
    """Read worker build metadata from environment with safe defaults."""
    return {
        "service": "worker",
        "version": _env_first("APP_VERSION", "BACKFIELD_APP_VERSION", default="0.1.0"),
        "git_sha": _env_first("GIT_SHA", "BACKFIELD_GIT_SHA", default="unknown"),
        "build_time": _env_first("BUILD_TIME", "BACKFIELD_BUILD_TIME", default="unknown"),
        "concurrency": os.environ.get("CELERY_WORKER_CONCURRENCY", _DEFAULT_CONCURRENCY).strip()
        or _DEFAULT_CONCURRENCY,
    }


def log_worker_startup() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    payload = {"event": "worker_startup", **read_worker_build_info()}
    logger.info(json.dumps(payload))


def _env_first(*names: str, default: str) -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default
