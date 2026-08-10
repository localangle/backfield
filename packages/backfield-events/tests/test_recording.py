"""Event recording, subscription matching, and output snapshot tests."""

from __future__ import annotations

import json

import pytest
from backfield_db import (
    AgateProcessedItem,
    AgateRunOutputArticle,
    BackfieldEvent,
    BackfieldWebhookDelivery,
    SubstrateArticle,
)
from backfield_events.contracts import RUN_COMPLETED_EVENT
from backfield_events.run_events import (
    materialize_run_output_snapshot,
    record_run_output_article,
    record_run_terminal_event,
)
from events_test_helpers import Tenancy, make_endpoint, make_run
from sqlmodel import Session, select


def _make_article(session: Session, project_id: int, headline: str) -> int:
    article = SubstrateArticle(project_id=project_id, headline=headline, text="body")
    session.add(article)
    session.flush()
    return int(article.id)


def test_terminal_event_records_exactly_one_event_and_delivery(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    make_endpoint(session, tenancy.project, tenancy.graph)
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"

    recorded = record_run_terminal_event(session, run)
    session.commit()

    assert recorded is not None
    events = session.exec(select(BackfieldEvent)).all()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == RUN_COMPLETED_EVENT
    assert event.project_id == tenancy.project.id
    assert event.graph_name == "Test Flow"
    assert event.run_id == run.id
    assert event.execution_attempt == 1
    payload = json.loads(event.payload_json)
    assert payload["outcome"] == "succeeded"
    assert payload["completion_reason"] == "completed"
    assert payload["failure_category"] is None

    deliveries = session.exec(select(BackfieldWebhookDelivery)).all()
    assert len(deliveries) == 1
    assert deliveries[0].state == "pending"


def test_no_event_when_webhooks_disabled(session: Session, tenancy: Tenancy) -> None:
    make_endpoint(session, tenancy.project, tenancy.graph)
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"

    assert record_run_terminal_event(session, run) is None
    session.commit()
    assert session.exec(select(BackfieldEvent)).all() == []


def test_unsubscribed_flow_gets_event_but_no_delivery(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    # Endpoint subscribed to a different flow in the same project.
    from backfield_db import AgateGraph

    other_graph = AgateGraph(
        name="Other Flow",
        spec_json="{}",
        project_id=int(tenancy.project.id),
    )
    session.add(other_graph)
    session.flush()
    make_endpoint(session, tenancy.project, other_graph)

    run = make_run(session, tenancy.graph)
    run.status = "succeeded"
    recorded = record_run_terminal_event(session, run)
    session.commit()

    assert recorded is not None
    assert recorded.delivery_ids == ()
    assert len(session.exec(select(BackfieldEvent)).all()) == 1
    assert session.exec(select(BackfieldWebhookDelivery)).all() == []


@pytest.mark.parametrize(
    ("endpoint_status", "expects_delivery"),
    [("active", True), ("pending", False), ("paused", False), ("disabled", False)],
)
def test_only_active_endpoints_receive_deliveries(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
    endpoint_status: str,
    expects_delivery: bool,
) -> None:
    make_endpoint(session, tenancy.project, tenancy.graph, status=endpoint_status)
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"
    record_run_terminal_event(session, run)
    session.commit()
    deliveries = session.exec(select(BackfieldWebhookDelivery)).all()
    assert bool(deliveries) is expects_delivery


def test_outcome_filter_skips_non_matching_runs(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    make_endpoint(session, tenancy.project, tenancy.graph, outcomes=["failed"])
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"
    record_run_terminal_event(session, run)
    session.commit()
    assert session.exec(select(BackfieldWebhookDelivery)).all() == []
    # The feed still records the event regardless of matching endpoints.
    assert len(session.exec(select(BackfieldEvent)).all()) == 1


def test_cancelled_run_normalizes_outcome(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    run = make_run(session, tenancy.graph)
    run.status = "failed"
    run.error_message = "Run cancelled by user"
    record_run_terminal_event(session, run)
    session.commit()
    event = session.exec(select(BackfieldEvent)).one()
    payload = json.loads(event.payload_json)
    assert payload["outcome"] == "failed"
    assert payload["completion_reason"] == "cancelled"
    assert payload["failure_category"] == "cancelled"


def test_snapshot_copies_succeeded_items_and_preserves_prior_attempts(
    session: Session,
    tenancy: Tenancy,
) -> None:
    run = make_run(session, tenancy.graph)
    article_one = _make_article(session, int(tenancy.project.id), "one")
    article_two = _make_article(session, int(tenancy.project.id), "two")

    item_one = AgateProcessedItem(
        run_id=run.id,
        status="succeeded",
        substrate_article_id=article_one,
    )
    item_two = AgateProcessedItem(run_id=run.id, status="failed")
    session.add(item_one)
    session.add(item_two)
    session.flush()

    run.status = "failed"  # partial failure keeps successfully committed outputs
    assert materialize_run_output_snapshot(session, run) == 1
    session.commit()

    # Explicit rerun: attempt 2 succeeds with both articles.
    run.execution_attempt = 2
    item_two.status = "succeeded"
    item_two.substrate_article_id = article_two
    session.add(item_two)
    run.status = "succeeded"
    assert materialize_run_output_snapshot(session, run) == 2
    session.commit()

    rows = session.exec(select(AgateRunOutputArticle)).all()
    attempt_one = {r.article_id for r in rows if r.execution_attempt == 1}
    attempt_two = {r.article_id for r in rows if r.execution_attempt == 2}
    assert attempt_one == {article_one}
    assert attempt_two == {article_one, article_two}


def test_record_run_output_article_is_idempotent(session: Session, tenancy: Tenancy) -> None:
    run = make_run(session, tenancy.graph)
    article = _make_article(session, int(tenancy.project.id), "one")
    assert record_run_output_article(
        session,
        run_id=run.id,
        execution_attempt=1,
        article_id=article,
        processed_item_id=None,
    )
    assert not record_run_output_article(
        session,
        run_id=run.id,
        execution_attempt=1,
        article_id=article,
        processed_item_id=None,
    )
    session.commit()
    assert len(session.exec(select(AgateRunOutputArticle)).all()) == 1


def test_rollback_leaves_no_event_or_delivery(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    make_endpoint(session, tenancy.project, tenancy.graph)
    run = make_run(session, tenancy.graph)
    session.commit()
    run.status = "succeeded"
    recorded = record_run_terminal_event(session, run)
    assert recorded is not None
    session.rollback()
    assert session.exec(select(BackfieldEvent)).all() == []
    assert session.exec(select(BackfieldWebhookDelivery)).all() == []
