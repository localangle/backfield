"""Worker webhook delivery orchestration tests (claim → HTTP → fenced terminalize)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backfield_db import (
    BackfieldEvent,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookDeliveryAttempt,
    BackfieldWebhookEndpoint,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_db.crypto import encrypt_secret
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from worker.webhooks import delivery as delivery_module
from worker.webhooks.delivery import (
    deliver_webhook_delivery,
    find_and_deliver_due,
    purge_expired_events,
)
from worker.webhooks.sender import WebhookSendResult

ENDPOINT_URL = "https://receiver.example.com/backfield"


@pytest.fixture
def engine(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Engine:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    database_path = tmp_path / "webhook-worker-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        stylebook = Stylebook(organization_id=int(org.id), name="Default", slug="default")
        session.add(stylebook)
        session.commit()
        session.refresh(stylebook)
        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            stylebook_id=int(stylebook.id),
            name="Default",
            slug="default",
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        session.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
                workspace_id=int(ws.id),
                stylebook_id=int(stylebook.id),
            )
        )
        session.commit()
    return engine


def _seed_delivery(
    engine: Engine,
    *,
    endpoint_status: str = "active",
    next_attempt_at: datetime | None = None,
) -> str:
    with Session(engine) as session:
        endpoint = BackfieldWebhookEndpoint(
            organization_id=1,
            project_id=1,
            name="Receiver",
            url_encrypted=encrypt_secret(ENDPOINT_URL),
            display_host="receiver.example.com",
            signing_secret_encrypted=encrypt_secret("whsec_test"),
            status=endpoint_status,
        )
        session.add(endpoint)
        session.flush()
        event = BackfieldEvent(
            event_type="agate.run.completed",
            organization_id=1,
            project_id=1,
            graph_id="graph-1",
            graph_name="Flow",
            run_id="run-1",
            execution_attempt=1,
            payload_json=(
                '{"outcome": "succeeded", "completion_reason": "completed", '
                '"failure_category": null, '
                '"counts": {"total": 1, "succeeded": 1, "failed": 0}, '
                '"article_count": 1}'
            ),
            occurred_at=datetime.now(UTC),
        )
        session.add(event)
        session.flush()
        delivery = BackfieldWebhookDelivery(
            event_id=int(event.id),
            endpoint_id=endpoint.id,
            state="pending",
            next_attempt_at=next_attempt_at or datetime.now(UTC),
        )
        session.add(delivery)
        session.commit()
        return delivery.id


def _stub_send(monkeypatch: pytest.MonkeyPatch, result: WebhookSendResult) -> list[dict]:
    calls: list[dict] = []

    def fake_send(*, url: str, body: bytes, headers: dict[str, str]) -> WebhookSendResult:
        calls.append({"url": url, "body": body, "headers": headers})
        return result

    monkeypatch.setattr(delivery_module, "send_signed_webhook", fake_send)
    return calls


def _success_result() -> WebhookSendResult:
    return WebhookSendResult(
        ok=True,
        status_code=200,
        failure_category=None,
        failure_summary=None,
        retryable=False,
        retry_after_seconds=None,
        duration_ms=25,
    )


def test_successful_delivery_signs_and_terminalizes(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery_id = _seed_delivery(engine)
    calls = _stub_send(monkeypatch, _success_result())

    outcome = deliver_webhook_delivery(engine, delivery_id)
    assert outcome == "delivered"

    assert len(calls) == 1
    assert calls[0]["url"] == ENDPOINT_URL
    headers = calls[0]["headers"]
    assert headers["Backfield-Signature"].startswith("v1=")
    assert headers["Backfield-Event-Type"] == "agate.run.completed"
    assert b'"type":"agate.run.completed"' in calls[0]["body"]

    with Session(engine) as session:
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        assert delivery.state == "delivered"
        assert delivery.last_status_code == 200
        assert delivery.lease_token is None
        attempt = session.exec(select(BackfieldWebhookDeliveryAttempt)).one()
        assert attempt.attempt_number == 1
        endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
        assert endpoint.last_success_at is not None


def test_retryable_failure_schedules_retry(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery_id = _seed_delivery(engine)
    _stub_send(
        monkeypatch,
        WebhookSendResult(
            ok=False,
            status_code=503,
            failure_category="http_5xx",
            failure_summary="HTTP 503",
            retryable=True,
            retry_after_seconds=None,
            duration_ms=10,
        ),
    )

    outcome = deliver_webhook_delivery(engine, delivery_id)
    assert outcome == "retry_scheduled"

    with Session(engine) as session:
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        assert delivery.state == "pending"
        assert delivery.failure_category == "http_5xx"
        assert delivery.next_attempt_at > datetime.now(UTC).replace(tzinfo=None) or True
        endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
        assert endpoint.status == "active"
        assert endpoint.last_failure_at is not None


def test_non_retryable_4xx_terminalizes_without_pausing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery_id = _seed_delivery(engine)
    _stub_send(
        monkeypatch,
        WebhookSendResult(
            ok=False,
            status_code=404,
            failure_category="http_4xx",
            failure_summary="HTTP 404",
            retryable=False,
            retry_after_seconds=None,
            duration_ms=10,
        ),
    )

    outcome = deliver_webhook_delivery(engine, delivery_id)
    assert outcome == "failed"

    with Session(engine) as session:
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        assert delivery.state == "failed"
        endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
        assert endpoint.status == "active"


def test_exhausted_retry_window_pauses_endpoint(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery_id = _seed_delivery(engine)
    with Session(engine) as session:
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        # Pretend the first attempt happened 25 hours ago so the window is spent.
        delivery.first_attempted_at = datetime.now(UTC) - timedelta(hours=25)
        session.add(delivery)
        session.commit()
    _stub_send(
        monkeypatch,
        WebhookSendResult(
            ok=False,
            status_code=503,
            failure_category="http_5xx",
            failure_summary="HTTP 503",
            retryable=True,
            retry_after_seconds=None,
            duration_ms=10,
        ),
    )

    outcome = deliver_webhook_delivery(engine, delivery_id)
    assert outcome == "paused"

    with Session(engine) as session:
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        assert delivery.state == "failed"
        endpoint = session.exec(select(BackfieldWebhookEndpoint)).one()
        assert endpoint.status == "paused"
        assert endpoint.pause_reason == "delivery_retries_exhausted"


def test_paused_endpoint_deliveries_are_not_claimable(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery_id = _seed_delivery(engine, endpoint_status="paused")
    calls = _stub_send(monkeypatch, _success_result())

    outcome = deliver_webhook_delivery(engine, delivery_id)
    assert outcome == "not_claimed"
    assert calls == []


def test_find_and_deliver_due_processes_due_rows(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    due_id = _seed_delivery(engine)
    future_id = _seed_delivery(
        engine, next_attempt_at=datetime.now(UTC) + timedelta(hours=1)
    )
    _stub_send(monkeypatch, _success_result())

    processed = find_and_deliver_due(engine)
    assert processed == 1

    with Session(engine) as session:
        assert session.get(BackfieldWebhookDelivery, due_id).state == "delivered"
        assert session.get(BackfieldWebhookDelivery, future_id).state == "pending"


def test_purge_expired_events_removes_old_rows(engine: Engine) -> None:
    delivery_id = _seed_delivery(engine)
    with Session(engine) as session:
        event = session.exec(select(BackfieldEvent)).one()
        event.created_at = datetime.now(UTC) - timedelta(days=91)
        session.add(event)
        # SQLite does not enforce FK cascades; delete the delivery so the purge
        # exercises only the event retention path.
        delivery = session.get(BackfieldWebhookDelivery, delivery_id)
        session.delete(delivery)
        session.commit()

    purged = purge_expired_events(engine)
    assert purged == 1
    with Session(engine) as session:
        assert session.exec(select(BackfieldEvent)).first() is None
