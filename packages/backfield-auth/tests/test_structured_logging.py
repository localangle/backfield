"""Structured JSON logging tests."""

from __future__ import annotations

import json
import logging

import pytest
from backfield_auth.log_context import bind_log_context, clear_log_context, reset_log_context
from backfield_auth.request_logging_middleware import RequestLoggingMiddleware
from backfield_auth.structured_logging import (
    JsonLogFormatter,
    configure_structured_logging,
    log_event,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_json_formatter_emits_standard_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v1.2.3")
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("BACKFIELD_ENV", "test")

    formatter = JsonLogFormatter("agate-api")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.event = "test_event"
    record.method = "GET"

    payload = json.loads(formatter.format(record))
    assert payload["service"] == "agate-api"
    assert payload["environment"] == "test"
    assert payload["version"] == "v1.2.3"
    assert payload["git_sha"] == "abc123"
    assert payload["event"] == "test_event"
    assert payload["method"] == "GET"
    assert payload["message"] == "hello"


def test_log_event_includes_context_fields() -> None:
    logger = logging.getLogger("test.structured.event")
    formatter = JsonLogFormatter("core-api")
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(formatter.format(record))

    logger.handlers.clear()
    logger.addHandler(_CaptureHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False

    reset = bind_log_context(
        request_id="req-1",
        client="pytest",
        run_id="run-9",
        job_id="job-3",
    )
    try:
        log_event(logger, "unit_test", path="/demo")
    finally:
        reset_log_context(reset)
        clear_log_context()

    payload = json.loads(captured[-1])
    assert payload["event"] == "unit_test"
    assert payload["request_id"] == "req-1"
    assert payload["client"] == "pytest"
    assert payload["run_id"] == "run-9"
    assert payload["job_id"] == "job-3"
    assert payload["path"] == "/demo"


def test_request_logging_middleware_emits_json_access_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKFIELD_ENV", "test")
    request_logger = logging.getLogger("backfield.request")
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            for handler in logging.getLogger().handlers:
                if getattr(handler, "_backfield_structured_json", False):
                    captured.append(handler.formatter.format(record))
                    return

    request_logger.handlers.clear()
    request_logger.addHandler(_CaptureHandler())
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = True
    configure_structured_logging("stylebook-api")

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, service_name="stylebook-api")

    @app.get("/demo")
    def demo() -> dict[str, str]:
        return {"ok": "true"}

    client = TestClient(app)
    response = client.get("/demo", headers={"X-Request-ID": "req-demo", "User-Agent": "pytest"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "req-demo"

    assert captured
    payload = json.loads(captured[-1])
    assert payload["event"] == "http_request"
    assert payload["service"] == "stylebook-api"
    assert payload["request_id"] == "req-demo"
    assert payload["path"] == "/demo"
    assert payload["status_code"] == 200
    assert "duration_ms" in payload


def test_configure_structured_logging_is_idempotent() -> None:
    def _structured_handlers() -> list[logging.Handler]:
        return [
            handler
            for handler in logging.getLogger().handlers
            if getattr(handler, "_backfield_structured_json", False)
        ]

    configure_structured_logging("idempotent-service")
    after_first = len(_structured_handlers())
    configure_structured_logging("idempotent-service")
    assert len(_structured_handlers()) == after_first
    assert after_first >= 1
