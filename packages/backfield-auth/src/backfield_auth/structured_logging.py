"""Structured JSON logging for Backfield services."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging import LogRecord
from typing import Any

from backfield_observability.identity import read_runtime_identity

from backfield_auth.log_context import read_log_context

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

# Preserve CloudWatch EMF metadata if a LogRecord ever carries it.
def read_environment() -> str:
    return read_runtime_identity("unknown").environment


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per log line with shared service metadata."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._identity = read_runtime_identity(service_name)

    def format(self, record: LogRecord) -> str:
        severity = record.levelname.lower()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": severity,
            "severity": severity,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service_name,
            "environment": self._identity.environment,
            "version": self._identity.version,
            "git_sha": self._identity.git_sha,
        }
        if self._identity.client:
            payload["client"] = self._identity.client
        payload.update(read_log_context())
        payload.update(_structured_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _structured_fields(record: LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _LOG_RECORD_STANDARD:
            continue
        # Drop logging-internal attrs; keep CloudWatch EMF `_aws` if present.
        if key.startswith("_") and key != "_aws":
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
