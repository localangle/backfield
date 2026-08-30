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

from tests.project_helpers import project_ownership_fields


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
        project = BackfieldProject(
            **project_ownership_fields(session, org.id),
            organization_id=org.id,
            name="General",
            slug="general",
        )
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


def test_project_stats_avg_cost_per_item_with_two_items() -> None:
    from datetime import UTC, datetime, timedelta

    from api.routers.projects import _avg_ai_cost_stats_for_terminal_items
    from backfield_db import AgateProcessedItem, BackfieldAiCallRecord

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-items")
        session.add(org)
        session.commit()
        session.refresh(org)
        project = BackfieldProject(
            **project_ownership_fields(session, org.id),
            organization_id=org.id,
            name="Items",
            slug="items",
        )
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
        session.refresh(run)

        started = datetime.now(UTC) - timedelta(seconds=20)
        ended = datetime.now(UTC)
        item_a = AgateProcessedItem(
            run_id=run.id,
            status="succeeded",
            started_at=started,
            created_at=started,
            updated_at=ended,
        )
        item_b = AgateProcessedItem(
            run_id=run.id,
            status="succeeded",
            started_at=started,
            created_at=started,
            updated_at=ended,
        )
        session.add(item_a)
        session.add(item_b)
        session.commit()
        session.refresh(item_a)
        session.refresh(item_b)

        session.add(
            BackfieldAiCallRecord(
                project_id=project.id,
                run_id=run.id,
                processed_item_id=item_a.id,
                provider="openai",
                provider_model_id="gpt-test",
                status="succeeded",
                estimated_cost=Decimal("0.20"),
                currency="USD",
            )
        )
        session.add(
            BackfieldAiCallRecord(
                project_id=project.id,
                run_id=run.id,
                processed_item_id=item_b.id,
                provider="openai",
                provider_model_id="gpt-test",
                status="succeeded",
                estimated_cost=Decimal("0.40"),
                currency="USD",
            )
        )
        session.commit()

        avg, incomplete, currency = _avg_ai_cost_stats_for_terminal_items(
            session,
            int(project.id),
            [graph.id],
        )
        assert avg is not None
        assert abs(avg - Decimal("0.3")) < Decimal("0.0001")
        assert incomplete is False
        assert currency == "USD"

        stats = _project_stats(session, project)
        assert stats.avg_estimated_ai_cost_per_item is not None
        assert abs(stats.avg_estimated_ai_cost_per_item - Decimal("0.3")) < Decimal("0.0001")
        assert stats.avg_duration_ms_per_item is not None
