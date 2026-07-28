"""Runtime identity and CloudWatch EMF helpers for Backfield services."""

from backfield_observability.identity import (
    SERVICE_NAMES,
    RuntimeIdentity,
    read_environment,
    read_runtime_identity,
    require_client_for_metrics,
)
from backfield_observability.lifecycle import (
    api_identity,
    emit_item_terminal,
    emit_run_terminal,
    emit_worker_lost,
    worker_identity,
)
from backfield_observability.metrics import (
    MetricKind,
    MetricUnit,
    log_metric,
)

__all__ = [
    "SERVICE_NAMES",
    "MetricKind",
    "MetricUnit",
    "RuntimeIdentity",
    "api_identity",
    "emit_item_terminal",
    "emit_run_terminal",
    "emit_worker_lost",
    "log_metric",
    "read_environment",
    "read_runtime_identity",
    "require_client_for_metrics",
    "worker_identity",
]
