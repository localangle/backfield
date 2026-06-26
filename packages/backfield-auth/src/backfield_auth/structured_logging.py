"""Structured JSON logging for Backfield services."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from logging import LogRecord
from typing import Any

from backfield_auth.log_context import read_log_context
from backfield_auth.service_health import read_build_info

_HANDLER_FLAG = "_backfield_structured_json"

_LOG_RECORD_STANDARD = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        "message",
    }
)


def read_environment() -> str:
    for name in ("BACKFIELD_ENV", "ENVIRONMENT"):
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return "development"


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per log line with shared service metadata."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._build_info = read_build_info(service_name)
        self._environment = read_environment()

    def format(self, record: LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service_name,
            "environment": self._environment,
            "version": self._build_info.version,
            "git_sha": self._build_info.git_sha,
        }
        payload.update(read_log_context())
        payload.update(_structured_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _structured_fields(record: LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _LOG_RECORD_STANDARD or key.startswith("_"):
            continue
        if value is not None:
            fields[key] = value
    return fields


def configure_structured_logging(
    service_name: str,
    *,
    level: int = logging.INFO,
) -> None:
    """Attach a JSON stderr handler to the root logger (idempotent per process)."""
    root = logging.getLogger()
    if any(getattr(handler, _HANDLER_FLAG, False) for handler in root.handlers):
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonLogFormatter(service_name))
    setattr(handler, _HANDLER_FLAG, True)
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log a structured event; ``event`` and ``fields`` appear as JSON keys."""
    extras = {key: value for key, value in fields.items() if value is not None}
    extras["event"] = event
    logger.log(level, event, extra=extras)
