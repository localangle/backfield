"""Lifecycle metric helpers for Agate run/item terminal transitions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from backfield_observability.identity import RuntimeIdentity, read_runtime_identity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric

_TERMINAL = frozenset({"succeeded", "failed"})


def worker_identity() -> RuntimeIdentity:
    return read_runtime_identity("worker")


def api_identity(service_name: str) -> RuntimeIdentity:
    return read_runtime_identity(service_name)


def emit_run_terminal(
    *,
    previous_status: str,
    new_status: str,
    identity: RuntimeIdentity,
    correlation: Mapping[str, str] | None = None,
) -> bool:
    """Emit run counter when status newly becomes succeeded or failed."""
    if new_status not in _TERMINAL or previous_status == new_status:
        return False
    if previous_status in _TERMINAL and previous_status != new_status:
        # Conflicting re-terminalization should not double-count.
        return False
    name = "runs_completed_total" if new_status == "succeeded" else "runs_failed_total"
    return log_metric(
        name,
        1,
        identity=identity,
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
        correlation=correlation,
    )


def emit_item_terminal(
    *,
    previous_status: str,
    new_status: str,
    identity: RuntimeIdentity,
    started_at: datetime | None,
    finished_at: datetime,
    correlation: Mapping[str, str] | None = None,
) -> bool:
    """Emit item counter (+ duration) when status newly becomes succeeded or failed."""
    if new_status not in _TERMINAL or previous_status == new_status:
        return False
    if previous_status in ("skipped",) or previous_status in _TERMINAL:
        return False
    name = "items_completed_total" if new_status == "succeeded" else "items_failed_total"
    emitted = log_metric(
        name,
        1,
        identity=identity,
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
        correlation=correlation,
    )
    if started_at is not None:
        if started_at.tzinfo is None:
            start = started_at.replace(tzinfo=finished_at.tzinfo)
        else:
            start = started_at
        duration = max(0.0, (finished_at - start).total_seconds())
        log_metric(
            "item_duration_seconds",
            duration,
            identity=identity,
            unit=MetricUnit.SECONDS,
            kind=MetricKind.DISTRIBUTION,
            correlation=correlation,
        )
    return emitted


def emit_worker_lost(*, identity: RuntimeIdentity | None = None) -> bool:
    """Best-effort in-app worker-loss counter (incomplete vs ECS stop reasons)."""
    return log_metric(
        "worker_lost_total",
        1,
        identity=identity or worker_identity(),
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
    )
