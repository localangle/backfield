"""Typed event framework tests: registry, article/canonical events, all-flows
matching, per-transaction coalescing, and suppression."""

from __future__ import annotations

import json

from backfield_db import (
    BackfieldEvent,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
    SubstrateArticle,
)
from backfield_events import (
    event_type_is_flow_scoped,
    record_article_created,
    record_article_updated,
    record_canonical_created,
    record_canonical_evidence_changed,
    record_canonical_merged,
    registered_event_types,
)
from backfield_events.contracts import (
    ARTICLE_CREATED_EVENT,
    ARTICLE_UPDATED_EVENT,
    CANONICAL_CREATED_EVENT,
    CANONICAL_EVIDENCE_CHANGED_EVENT,
    CANONICAL_MERGED_EVENT,
    RUN_COMPLETED_EVENT,
)
from backfield_events.run_events import record_run_terminal_event
from events_test_helpers import Tenancy, make_run
from sqlmodel import Session, select


def _make_article(session: Session, project_id: int, headline: str) -> int:
    article = SubstrateArticle(project_id=project_id, headline=headline, text="body")
    session.add(article)
    session.flush()
    return int(article.id)


def _make_endpoint_with_subscriptions(
    session: Session,
    tenancy: Tenancy,
    subscriptions: list[tuple[str, str | None]],
) -> BackfieldWebhookEndpoint:
    """Active endpoint with explicit (event_type, graph_id) subscription rows."""
    endpoint = BackfieldWebhookEndpoint(
        organization_id=int(tenancy.project.organization_id),
        project_id=int(tenancy.project.id),
        name="Receiver",
        url_encrypted="not-a-real-ciphertext",
        display_host="hooks.example.com",
        signing_secret_encrypted="not-a-real-ciphertext",
        status="active",
    )
    session.add(endpoint)
    session.flush()
    for event_type, graph_id in subscriptions:
        session.add(
            BackfieldWebhookSubscription(
                endpoint_id=endpoint.id,
                event_type=event_type,
                graph_id=graph_id,
            )
        )
    session.flush()
    return endpoint


def test_registry_contains_all_public_event_types() -> None:
    types = registered_event_types()
    assert set(types) == {
        "agate.run.completed",
        "agate.article.created",
        "agate.article.updated",
        "stylebook.canonical.created",
        "stylebook.canonical.updated",
        "stylebook.canonical.deleted",
        "stylebook.canonical.merged",
        "stylebook.canonical.evidence.changed",
    }
    assert event_type_is_flow_scoped(RUN_COMPLETED_EVENT)
    assert event_type_is_flow_scoped(ARTICLE_CREATED_EVENT)
    assert not event_type_is_flow_scoped(CANONICAL_CREATED_EVENT)


def test_article_created_event_scopes_and_delivers(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    _make_endpoint_with_subscriptions(
        session, tenancy, [(ARTICLE_CREATED_EVENT, tenancy.graph.id)]
    )
    run = make_run(session, tenancy.graph)
    article_id = _make_article(session, int(tenancy.project.id), "Hello")

    recorded = record_article_created(
        session,
        run_id=run.id,
        article_id=article_id,
        headline="Hello",
    )
    session.commit()

    assert len(recorded) == 1
    event = session.exec(select(BackfieldEvent)).one()
    assert event.event_type == ARTICLE_CREATED_EVENT
    assert event.article_id == article_id
    assert event.run_id == run.id
    assert json.loads(event.payload_json) == {"headline": "Hello"}
    assert len(session.exec(select(BackfieldWebhookDelivery)).all()) == 1


def test_article_updated_coalesces_per_article_per_transaction(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    run = make_run(session, tenancy.graph)
    article_id = _make_article(session, int(tenancy.project.id), "Hello")

    first = record_article_updated(
        session,
        run_id=run.id,
        article_id=article_id,
        headline="Hello",
        change="reprocessed",
        content_changed=True,
    )
    second = record_article_updated(
        session,
        run_id=run.id,
        article_id=article_id,
        headline="Hello",
        change="metadata",
    )
    session.commit()

    assert len(first) == 1
    assert second == ()
    events = session.exec(select(BackfieldEvent)).all()
    assert [e.event_type for e in events] == [ARTICLE_UPDATED_EVENT]

    # A new transaction records the article again.
    third = record_article_updated(
        session,
        run_id=run.id,
        article_id=article_id,
        headline="Hello",
        change="metadata",
    )
    session.commit()
    assert len(third) == 1


def test_all_flows_subscription_matches_any_flow(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    _make_endpoint_with_subscriptions(session, tenancy, [(RUN_COMPLETED_EVENT, None)])
    run = make_run(session, tenancy.graph)
    run.status = "succeeded"

    recorded = record_run_terminal_event(session, run)
    session.commit()

    assert recorded is not None
    assert len(recorded.delivery_ids) == 1


def test_canonical_event_fans_out_to_every_stylebook_project(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    sibling = BackfieldProject(
        organization_id=int(tenancy.project.organization_id),
        workspace_id=int(tenancy.project.workspace_id),
        stylebook_id=int(tenancy.project.stylebook_id),
        name="Sibling Project",
        slug="sibling-project",
    )
    session.add(sibling)
    session.flush()
    _make_endpoint_with_subscriptions(session, tenancy, [(CANONICAL_CREATED_EVENT, None)])

    recorded = record_canonical_created(
        session,
        stylebook_id=int(tenancy.project.stylebook_id),
        entity_type="location",
        canonical_id="canon-1",
        label="City Hall",
    )
    session.commit()

    assert len(recorded) == 2  # one event row per project on the stylebook
    events = session.exec(select(BackfieldEvent)).all()
    assert {e.project_id for e in events} == {int(tenancy.project.id), int(sibling.id)}
    assert all(e.entity_type == "location" and e.entity_id == "canon-1" for e in events)
    # Only the subscribed project's endpoint gets a delivery.
    assert len(session.exec(select(BackfieldWebhookDelivery)).all()) == 1


def test_merge_suppresses_evidence_events_and_records_merge(
    session: Session,
    tenancy: Tenancy,
    webhooks_on: None,
) -> None:
    stylebook_id = int(tenancy.project.stylebook_id)
    recorded_merge = record_canonical_merged(
        session,
        stylebook_id=stylebook_id,
        entity_type="location",
        source_canonical_id="canon-src",
        target_canonical_id="canon-dst",
        label="Old Entry",
    )
    # Evidence churn from relinking during the merge is swallowed.
    suppressed = record_canonical_evidence_changed(
        session,
        stylebook_id=stylebook_id,
        entity_type="location",
        canonical_id="canon-dst",
        label="Kept Entry",
        change="substrate_linked",
    )
    session.commit()

    assert len(recorded_merge) == 1
    assert suppressed == ()
    events = session.exec(select(BackfieldEvent)).all()
    assert [e.event_type for e in events] == [CANONICAL_MERGED_EVENT]
    assert json.loads(events[0].payload_json)["merged_into"] == "canon-dst"

    # Suppression is transaction-scoped: after commit, evidence records again.
    after = record_canonical_evidence_changed(
        session,
        stylebook_id=stylebook_id,
        entity_type="location",
        canonical_id="canon-dst",
        label="Kept Entry",
        change="substrate_unlinked",
    )
    session.commit()
    assert len(after) == 1
    evidence_events = [
        e
        for e in session.exec(select(BackfieldEvent)).all()
        if e.event_type == CANONICAL_EVIDENCE_CHANGED_EVENT
    ]
    assert len(evidence_events) == 1
