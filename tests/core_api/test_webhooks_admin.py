"""Org-admin webhook endpoint management API tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from agate_runtime.types import GraphSpec
from backfield_db import (
    AgateGraph,
    BackfieldEvent,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
    BackfieldWorkspace,
)
from backfield_db.crypto import decrypt_secret
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api import webhook_verification
from core_api.deps import get_session
from core_api.main import app
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from tests.core_api.auth_helpers import attach_test_engine, seed_and_login
from tests.project_helpers import project_ownership_fields

ENDPOINT_URL = "https://receiver.example.com/backfield"


@pytest.fixture
def webhooks_client(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    database_path = tmp_path / "webhooks-admin-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        oid = int(org.id)
        sb = ensure_default_stylebook_for_organization(s, oid)
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=int(sb.id),  # type: ignore[arg-type]
            name="Default Workspace",
            slug="default",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        s.add(
            BackfieldProject(
                **project_ownership_fields(s, oid, workspace_id=int(ws.id)),
                name="General",
                slug="general",
                organization_id=oid,
                workspace_id=int(ws.id),
            )
        )
        s.commit()
        s.add(
            AgateGraph(
                id="graph-webhook-flow",
                name="Webhook flow",
                spec_json=GraphSpec(name="flow", nodes=[], edges=[]).model_dump_json(),
                project_id=1,
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield attach_test_engine(TestClient(app), engine)
    finally:
        app.dependency_overrides.clear()


def _login_admin(client: TestClient) -> None:
    seed_and_login(client, "webhooks@example.com", "webhooks-secret-12")


def _create_endpoint(client: TestClient, **overrides) -> dict:
    body = {
        "project_id": 1,
        "name": "CMS updates",
        "url": ENDPOINT_URL,
        "flow_ids": ["graph-webhook-flow"],
        **overrides,
    }
    response = client.post("/v1/organizations/1/webhook-endpoints", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_webhook_endpoints_require_session(webhooks_client: TestClient) -> None:
    response = webhooks_client.get("/v1/organizations/1/webhook-endpoints")
    assert response.status_code == 401


def test_webhook_endpoints_require_org_admin(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    created = webhooks_client.post(
        "/v1/organizations/1/users",
        json={
            "email": "member@example.com",
            "password": "member-secret-12",
            "role": "member",
        },
    )
    assert created.status_code == 200
    login = webhooks_client.post(
        "/v1/auth/login",
        json={"email": "member@example.com", "password": "member-secret-12"},
    )
    assert login.status_code == 200
    response = webhooks_client.get("/v1/organizations/1/webhook-endpoints")
    assert response.status_code == 403


def test_create_endpoint_returns_secret_once_and_stays_pending(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    created = _create_endpoint(webhooks_client)
    assert created["signing_secret"].startswith("whsec_")
    endpoint = created["endpoint"]
    assert endpoint["status"] == "pending"
    assert endpoint["destination_host"] == "receiver.example.com"
    assert endpoint["flows"] == [
        {"flow_id": "graph-webhook-flow", "flow_name": "Webhook flow"}
    ]

    listed = webhooks_client.get("/v1/organizations/1/webhook-endpoints").json()
    assert len(listed) == 1
    assert "signing_secret" not in listed[0]

    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(BackfieldWebhookEndpoint)).one()
        assert decrypt_secret(row.signing_secret_encrypted) == created["signing_secret"]
        assert decrypt_secret(row.url_encrypted) == ENDPOINT_URL


def test_create_endpoint_rejects_http_url(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    response = webhooks_client.post(
        "/v1/organizations/1/webhook-endpoints",
        json={
            "project_id": 1,
            "name": "Insecure",
            "url": "http://receiver.example.com/hook",
            "flow_ids": ["graph-webhook-flow"],
        },
    )
    assert response.status_code == 400


def test_create_endpoint_rejects_flow_from_other_project(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        workspace = session.exec(select(BackfieldWorkspace)).one()
        sibling = BackfieldProject(
            **project_ownership_fields(
                session,
                int(workspace.organization_id),
                workspace_id=int(workspace.id),
            ),
            organization_id=int(workspace.organization_id),
            workspace_id=int(workspace.id),
            name="Sibling",
            slug="sibling",
        )
        session.add(sibling)
        session.flush()
        session.add(
            AgateGraph(
                id="graph-sibling-flow",
                name="Sibling flow",
                spec_json=GraphSpec(name="s", nodes=[], edges=[]).model_dump_json(),
                project_id=int(sibling.id),
            )
        )
        session.commit()

    response = webhooks_client.post(
        "/v1/organizations/1/webhook-endpoints",
        json={
            "project_id": 1,
            "name": "Cross project",
            "url": ENDPOINT_URL,
            "flow_ids": ["graph-sibling-flow"],
        },
    )
    assert response.status_code == 404


def test_endpoint_limit_is_enforced(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    for index in range(10):
        _create_endpoint(webhooks_client, name=f"Endpoint {index}")
    response = webhooks_client.post(
        "/v1/organizations/1/webhook-endpoints",
        json={
            "project_id": 1,
            "name": "One too many",
            "url": ENDPOINT_URL,
            "flow_ids": ["graph-webhook-flow"],
        },
    )
    assert response.status_code == 409


def test_successful_verification_test_activates_endpoint(
    webhooks_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]

    monkeypatch.setattr(
        webhook_verification,
        "_post_signed",
        lambda **kwargs: (200, None, None, 12),
    )
    response = webhooks_client.post(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["ok"] is True
    assert body["endpoint"]["status"] == "active"
    assert body["endpoint"]["verified_at"] is not None

    # Synthetic test events never enter the public feed.
    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        event = session.exec(select(BackfieldEvent)).one()
        assert event.is_test is True


def test_failed_verification_test_keeps_endpoint_pending(
    webhooks_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]

    monkeypatch.setattr(
        webhook_verification,
        "_post_signed",
        lambda **kwargs: (500, "http_5xx", "HTTP 500", 20),
    )
    response = webhooks_client.post(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["ok"] is False
    assert body["endpoint"]["status"] == "pending"
    assert body["endpoint"]["verified_at"] is None


def test_url_change_requires_reverification(
    webhooks_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]
    monkeypatch.setattr(
        webhook_verification,
        "_post_signed",
        lambda **kwargs: (200, None, None, 10),
    )
    webhooks_client.post(f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/test")

    patched = webhooks_client.patch(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}",
        json={"url": "https://other.example.com/hook"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "pending"
    assert patched.json()["verified_at"] is None
    assert patched.json()["destination_host"] == "other.example.com"


def test_rotate_secret_returns_new_secret_and_requires_reverification(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    created = _create_endpoint(webhooks_client)
    endpoint_id = created["endpoint"]["id"]

    rotated = webhooks_client.post(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/rotate-secret"
    )
    assert rotated.status_code == 200
    body = rotated.json()
    assert body["signing_secret"].startswith("whsec_")
    assert body["signing_secret"] != created["signing_secret"]
    assert body["secret_version"] == 2
    assert body["endpoint"]["status"] == "pending"


def test_activate_requires_prior_verification(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]
    response = webhooks_client.post(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/activate"
    )
    assert response.status_code == 409


def test_delete_endpoint_cascades_subscriptions(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]
    deleted = webhooks_client.delete(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}"
    )
    assert deleted.status_code == 204
    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        assert session.exec(select(BackfieldWebhookEndpoint)).first() is None
        assert session.exec(select(BackfieldWebhookSubscription)).first() is None


def test_replay_creates_new_delivery_for_active_endpoint(
    webhooks_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]
    monkeypatch.setattr(
        webhook_verification,
        "_post_signed",
        lambda **kwargs: (200, None, None, 10),
    )
    webhooks_client.post(f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/test")

    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        event = BackfieldEvent(
            event_type="agate.run.completed",
            organization_id=1,
            project_id=1,
            graph_id="graph-webhook-flow",
            graph_name="Webhook flow",
            run_id="run-1",
            execution_attempt=1,
            payload_json="{}",
            occurred_at=datetime.now(UTC),
        )
        session.add(event)
        session.flush()
        delivery = BackfieldWebhookDelivery(
            event_id=int(event.id),
            endpoint_id=endpoint_id,
            state="failed",
            attempt_count=3,
            next_attempt_at=datetime.now(UTC),
        )
        session.add(delivery)
        session.commit()
        source_delivery_id = delivery.id

    replayed = webhooks_client.post(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}"
        f"/deliveries/{source_delivery_id}/replay"
    )
    assert replayed.status_code == 200
    new_delivery_id = replayed.json()["delivery_id"]
    assert new_delivery_id != source_delivery_id

    history = webhooks_client.get(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}/deliveries"
    ).json()
    by_id = {row["id"]: row for row in history}
    assert by_id[new_delivery_id]["is_replay"] is True
    assert by_id[new_delivery_id]["state"] == "pending"


def test_cross_org_endpoint_is_not_visible(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]
    response = webhooks_client.get(
        f"/v1/organizations/2/webhook-endpoints/{endpoint_id}"
    )
    # The admin belongs to org 1, so org 2 access is rejected outright.
    assert response.status_code in (403, 404)


def test_event_types_catalog_lists_registered_types(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    response = webhooks_client.get("/v1/organizations/1/webhook-event-types")
    assert response.status_code == 200
    rows = {row["event_type"]: row["flow_scoped"] for row in response.json()}
    assert rows["agate.run.completed"] is True
    assert rows["agate.article.created"] is True
    assert rows["stylebook.canonical.created"] is False
    assert "backfield.webhook.test" not in rows


def test_create_endpoint_with_multiple_event_types_and_all_flows(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    created = _create_endpoint(
        webhooks_client,
        event_types=["agate.run.completed", "stylebook.canonical.updated"],
        flow_ids=None,
        all_flows=True,
    )
    endpoint = created["endpoint"]
    assert sorted(endpoint["event_types"]) == [
        "agate.run.completed",
        "stylebook.canonical.updated",
    ]
    assert endpoint["all_flows"] is True
    assert endpoint["flows"] == []

    with Session(webhooks_client.test_engine) as session:  # type: ignore[attr-defined]
        rows = session.exec(select(BackfieldWebhookSubscription)).all()
        # One all-flows row per event type; canonical rows are always graph-less.
        assert {(row.event_type, row.graph_id) for row in rows} == {
            ("agate.run.completed", None),
            ("stylebook.canonical.updated", None),
        }


def test_create_endpoint_rejects_unknown_event_type(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    response = webhooks_client.post(
        "/v1/organizations/1/webhook-endpoints",
        json={
            "project_id": 1,
            "name": "Bad type",
            "url": ENDPOINT_URL,
            "event_types": ["agate.run.started"],
            "all_flows": True,
        },
    )
    assert response.status_code == 400


def test_create_flow_scoped_endpoint_requires_flows_or_all_flows(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    response = webhooks_client.post(
        "/v1/organizations/1/webhook-endpoints",
        json={
            "project_id": 1,
            "name": "No flows",
            "url": ENDPOINT_URL,
            "event_types": ["agate.article.created"],
        },
    )
    assert response.status_code == 400


def test_patch_can_switch_between_explicit_flows_and_all_flows(
    webhooks_client: TestClient,
) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]

    patched = webhooks_client.patch(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}",
        json={"all_flows": True},
    )
    assert patched.status_code == 200
    assert patched.json()["all_flows"] is True
    assert patched.json()["flows"] == []

    back = webhooks_client.patch(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}",
        json={"all_flows": False, "flow_ids": ["graph-webhook-flow"]},
    )
    assert back.status_code == 200
    assert back.json()["all_flows"] is False
    assert back.json()["flows"] == [
        {"flow_id": "graph-webhook-flow", "flow_name": "Webhook flow"}
    ]


def test_patch_event_types_preserves_flow_selection(webhooks_client: TestClient) -> None:
    _login_admin(webhooks_client)
    endpoint_id = _create_endpoint(webhooks_client)["endpoint"]["id"]

    patched = webhooks_client.patch(
        f"/v1/organizations/1/webhook-endpoints/{endpoint_id}",
        json={"event_types": ["agate.run.completed", "agate.article.updated"]},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert sorted(body["event_types"]) == [
        "agate.article.updated",
        "agate.run.completed",
    ]
    assert body["flows"] == [
        {"flow_id": "graph-webhook-flow", "flow_name": "Webhook flow"}
    ]
