"""Median helpers for project stats rollups."""

from __future__ import annotations

from decimal import Decimal

from api.routers.projects import (
    _max_decimal,
    _max_ms,
    _median_decimal,
    _median_ms,
    _min_decimal,
    _min_ms,
)


def test_median_ms_empty() -> None:
    assert _median_ms([]) is None


def test_median_ms_odd_count() -> None:
    assert _median_ms([100.0, 200.0, 900.0]) == 200.0


def test_median_ms_even_count() -> None:
    assert _median_ms([100.0, 300.0]) == 200.0


def test_median_decimal_per_run_costs() -> None:
    costs = [Decimal("0.10"), Decimal("0.20"), Decimal("1.00")]
    assert _median_decimal(costs) == Decimal("0.20")


def test_min_max_ms() -> None:
    assert _min_ms([100.0, 200.0, 900.0]) == 100.0
    assert _max_ms([100.0, 200.0, 900.0]) == 900.0


def test_min_max_decimal_per_run_costs() -> None:
    costs = [Decimal("0.10"), Decimal("0.20"), Decimal("1.00")]
    assert _min_decimal(costs) == Decimal("0.10")
    assert _max_decimal(costs) == Decimal("1.00")
