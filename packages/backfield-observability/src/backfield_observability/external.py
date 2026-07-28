"""Helpers for external dependency request metrics and sanitized logs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from backfield_observability.identity import read_runtime_identity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric

T = TypeVar("T")

_logger = logging.getLogger("backfield.external_request")


def emit_external_request(
    *,
    operation: str,
    duration_seconds: float,
    failed: bool,
    service: str = "worker",
    provider: str | None = None,
    error_type: str | None = None,
    outcome: str | None = None,
) -> None:
    """Emit duration (+ failure counter) for one physical external request."""
    identity = read_runtime_identity(service)
    correlation = {
        key: value
        for key, value in {
            "provider": provider,
            "error_type": error_type,
            "outcome": outcome,
        }.items()
        if value
    }
    # Pull run/job/item from log context if bound by the caller process.
    try:
        from backfield_auth.log_context import read_log_context

        correlation.update(read_log_context())
    except Exception:
        pass

    log_metric(
        "external_request_duration_seconds",
        duration_seconds,
        identity=identity,
        unit=MetricUnit.SECONDS,
        kind=MetricKind.DISTRIBUTION,
        operation=operation,
        correlation=correlation,
    )
    if failed:
        log_metric(
            "external_request_failures_total",
            1,
            identity=identity,
            unit=MetricUnit.COUNT,
            kind=MetricKind.COUNTER,
            operation=operation,
            correlation=correlation,
        )
    _logger.info(
        "external_request",
        extra={
            "event": "external_request",
            "operation": operation,
            "provider": provider,
            "outcome": outcome or ("failure" if failed else "success"),
            "duration_seconds": round(duration_seconds, 4),
            "error_type": error_type,
        },
    )


def timed_external_call(
    *,
    operation: str,
    provider: str,
    service: str = "worker",
    call: Callable[[], T],
    is_failure: Callable[[T], bool] | None = None,
) -> T:
    """Run ``call``, emit metrics, and re-raise transport exceptions as failures."""
    started = time.perf_counter()
    try:
        result = call()
    except Exception as exc:
        emit_external_request(
            operation=operation,
            duration_seconds=time.perf_counter() - started,
            failed=True,
            service=service,
            provider=provider,
            error_type=type(exc).__name__,
            outcome="exception",
        )
        raise
    failed = bool(is_failure(result)) if is_failure is not None else False
    emit_external_request(
        operation=operation,
        duration_seconds=time.perf_counter() - started,
        failed=failed,
        service=service,
        provider=provider,
        error_type="provider_error" if failed else None,
        outcome="failure" if failed else "success",
    )
    return result


def sanitize_error_message(message: str | None, *, limit: int = 200) -> str | None:
    """Strip likely secrets and truncate provider exception text for logs."""
    if message is None:
        return None
    text = str(message)
    lowered = text.lower()
    for needle in ("api_key=", "authorization:", "password=", "secret=", "redis://", "postgres://"):
        if needle in lowered:
            return f"redacted:{needle.rstrip(':=')}"
    if "://" in text and "@" in text:
        return "redacted:url_with_credentials"
    return text[:limit]
