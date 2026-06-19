"""Mean helpers for project stats rollups."""

from __future__ import annotations

from decimal import Decimal

from api.routers.projects import (
    _max_decimal,
    _max_ms,
    _mean_decimal,
    _mean_ms,
    _min_decimal,
    _min_ms,
)


def test_mean_ms_empty() -> None:
    assert _mean_ms([]) is None


def test_mean_ms() -> None:
    assert _mean_ms([100.0, 200.0, 900.0]) == 400.0


def test_mean_decimal_per_run_costs() -> None:
    costs = [Decimal("0.10"), Decimal("0.20"), Decimal("1.00")]
    assert _mean_decimal(costs) == Decimal("0.4333333333333333333333333333")


def test_min_max_ms() -> None:
    assert _min_ms([100.0, 200.0, 900.0]) == 100.0
    assert _max_ms([100.0, 200.0, 900.0]) == 900.0


def test_min_max_decimal_per_run_costs() -> None:
    costs = [Decimal("0.10"), Decimal("0.20"), Decimal("1.00")]
    assert _min_decimal(costs) == Decimal("0.10")
    assert _max_decimal(costs) == Decimal("1.00")
