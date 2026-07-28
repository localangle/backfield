"""Golden-path CloudWatch EMF emission tests."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from backfield_observability.identity import RuntimeIdentity
from backfield_observability.metrics import MetricKind, MetricUnit, log_metric

_FIXTURES = Path(__file__).parent / "fixtures"


def _identity(*, client: str | None = "canary") -> RuntimeIdentity:
    return RuntimeIdentity(
        service="worker",
        environment="staging",
        version="main-abc123-amd64",
        git_sha="abc123",
        client=client,
    )


def test_log_metric_emits_valid_emf_with_required_dimensions() -> None:
    buf = io.StringIO()
    assert log_metric(
        "queue_depth",
        3,
        identity=_identity(),
        unit=MetricUnit.COUNT,
        kind=MetricKind.GAUGE,
        stream=buf,
    )

    payload = json.loads(buf.getvalue().strip())
    assert "_aws" in payload
    assert payload["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Backfield/Application"
    assert payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [
        ["Client", "Environment", "Service"]
    ]
    assert payload["_aws"]["CloudWatchMetrics"][0]["Metrics"] == [
        {"Name": "queue_depth", "Unit": "Count"}
    ]
    assert payload["Client"] == "canary"
    assert payload["Environment"] == "staging"
    assert payload["Service"] == "worker"
    assert payload["queue_depth"] == 3.0
    assert "Version" not in payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
    assert "run_id" not in payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]


def test_log_metric_operation_dimension_for_external_calls() -> None:
    buf = io.StringIO()
    log_metric(
        "external_request_failures_total",
        1,
        identity=_identity(),
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
        operation="geocoding",
        correlation={"run_id": "run-1"},
        stream=buf,
    )
    payload = json.loads(buf.getvalue().strip())
    assert payload["Operation"] == "geocoding"
    assert payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [
        ["Client", "Environment", "Service", "Operation"]
    ]
    # Correlation is log-only, not a CloudWatch dimension.
    assert payload["run_id"] == "run-1"
    assert "run_id" not in payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]


def test_log_metric_skips_when_client_missing() -> None:
    buf = io.StringIO()
    assert not log_metric(
        "runs_active",
        0,
        identity=_identity(client=None),
        unit=MetricUnit.COUNT,
        kind=MetricKind.GAUGE,
        stream=buf,
    )
    assert buf.getvalue() == ""


def test_log_metric_rejects_high_cardinality_operation() -> None:
    with pytest.raises(ValueError, match="Operation"):
        log_metric(
            "external_request_failures_total",
            1,
            identity=_identity(),
            unit=MetricUnit.COUNT,
            kind=MetricKind.COUNTER,
            operation="geocode.pelias.search",
            stream=io.StringIO(),
        )


def test_emf_golden_fixture_shape() -> None:
    """Fixture documents the exact EMF contract for backfield-cloud consumers."""
    buf = io.StringIO()
    log_metric(
        "items_completed_total",
        1,
        identity=_identity(),
        unit=MetricUnit.COUNT,
        kind=MetricKind.COUNTER,
        stream=buf,
    )
    payload = json.loads(buf.getvalue().strip())
    # Drop volatile timestamp fields for fixture comparison.
    payload.pop("timestamp", None)
    payload["_aws"].pop("Timestamp", None)
    expected = json.loads((_FIXTURES / "emf_items_completed_total.json").read_text())
    assert payload == expected
