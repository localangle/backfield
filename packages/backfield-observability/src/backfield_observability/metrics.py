"""CloudWatch Embedded Metric Format (EMF) emission helpers."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from backfield_observability.identity import RuntimeIdentity, require_client_for_metrics

DEFAULT_NAMESPACE = "Backfield/Application"

_ALLOWED_OPERATIONS = frozenset({"llm", "geocoding"})


class MetricKind(StrEnum):
    GAUGE = "gauge"
    COUNTER = "counter"
    DISTRIBUTION = "distribution"


class MetricUnit(StrEnum):
    COUNT = "Count"
    SECONDS = "Seconds"
    NONE = "None"


def log_metric(
    name: str,
    value: float | int,
    *,
    identity: RuntimeIdentity,
    unit: MetricUnit,
    kind: MetricKind,
    operation: str | None = None,
    namespace: str = DEFAULT_NAMESPACE,
    correlation: Mapping[str, str] | None = None,
    stream: Any | None = None,
) -> bool:
    """Emit one EMF JSON line to stderr.

    Returns True when a metric line was written. Skips emission when
    ``BACKFIELD_CLIENT`` is unset so local/dev does not invent a Client dimension.
    """
    client = require_client_for_metrics(identity)
    if client is None:
        return False
    if identity.service not in {"agate-api", "stylebook-api", "core-api", "worker"}:
        return False
    if operation is not None and operation not in _ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported Operation dimension: {operation!r}")

    dimension_keys = ["Client", "Environment", "Service"]
    payload: dict[str, Any] = {
        "Client": client,
        "Environment": identity.environment,
        "Service": identity.service,
        name: float(value) if not isinstance(value, bool) else value,
        "event": "cloudwatch_emf",
        "metric_name": name,
        "metric_kind": kind.value,
        "service": identity.service,
        "environment": identity.environment,
        "version": identity.version,
        "git_sha": identity.git_sha,
        "client": client,
        "severity": "info",
        "level": "info",
        "message": f"metric {name}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
    }
    if operation is not None:
        payload["Operation"] = operation
        dimension_keys.append("Operation")
    if correlation:
        for key, raw in correlation.items():
            if raw and key not in payload:
                payload[key] = raw

    payload["_aws"] = {
        "Timestamp": int(time.time() * 1000),
        "CloudWatchMetrics": [
            {
                "Namespace": namespace,
                "Dimensions": [dimension_keys],
                "Metrics": [{"Name": name, "Unit": unit.value}],
            }
        ],
    }

    out = stream if stream is not None else sys.stderr
    out.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    out.flush()
    return True
