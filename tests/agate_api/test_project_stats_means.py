"""Mean helpers for project stats rollups."""

from __future__ import annotations

from decimal import Decimal

from api.routers.projects import (
    _avg_ai_cost_stats_for_succeeded_runs,
    _max_decimal,
    _max_ms,
    _mean_decimal,
    _mean_ms,
    _min_decimal,
    _min_ms,
    _project_stats,
)
from backfield_db import AgateGraph, AgateRun, BackfieldOrganization, BackfieldProject
from sqlmodel import Session, SQLModel, create_engine


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


def test_project_stats_and_ai_cost_with_succeeded_run() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org")
        session.add(org)
        session.commit()
        session.refresh(org)
        project = BackfieldProject(organization_id=org.id, name="General", slug="general")
        session.add(project)
        session.commit()
        session.refresh(project)
        graph = AgateGraph(name="Flow", spec_json="{}", project_id=project.id)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        run = AgateRun(graph_id=graph.id, status="succeeded")
        session.add(run)
        session.commit()

        stats = _project_stats(session, project)
        assert stats.total_runs == 1
        assert stats.runs_succeeded == 1

        avg, incomplete, currency = _avg_ai_cost_stats_for_succeeded_runs(
            session,
            int(project.id),
            [graph.id],
        )
        assert avg == Decimal("0")
        assert incomplete is False
