"""Public event feed and run-articles endpoint tests."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from agate_runtime.types import GraphSpec
from backfield_db import (
    AgateGraph,
    AgateRun,
    AgateRunOutputArticle,
    BackfieldEvent,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_events.cursor import encode_event_cursor
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from tests.core_api.auth_helpers import attach_test_engine, seed_and_login
from tests.project_helpers import project_ownership_fields


@pytest.fixture
def events_client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "public-events-test.db"
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
                id="graph-events-flow",
                name="Events flow",
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


def _read_key(client: TestClient) -> str:
    seed_and_login(client, "events@example.com", "events-secret-12")
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "read"},
    )
    assert created.status_code == 200
    return str(created.json()["raw_key"])


def _run_completed_payload() -> str:
    return json.dumps(
        {
            "outcome": "succeeded",
            "completion_reason": "completed",
            "failure_category": None,
            "counts": {"total": 1, "succeeded": 1, "failed": 0},
            "article_count": 1,
        }
    )


def _seed_event(
    session: Session,
    *,
    graph_id: str = "graph-events-flow",
    run_id: str = "run-1",
    is_test: bool = False,
) -> BackfieldEvent:
    event = BackfieldEvent(
        event_type="agate.run.completed",
        organization_id=1,
        project_id=1,
        graph_id=graph_id,
        graph_name="Events flow",
        run_id=run_id,
        execution_attempt=1,
        payload_json=_run_completed_payload(),
        occurred_at=datetime.now(UTC),
        is_test=is_test,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def test_event_feed_requires_project_key(events_client: TestClient) -> None:
    response = events_client.get("/public/v1/projects/general/events")
    assert response.status_code == 401


def test_event_feed_orders_ascending_and_pages_by_cursor(
    events_client: TestClient,
) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        for index in range(3):
            _seed_event(session, run_id=f"run-{index}")

    headers = {"Authorization": f"Bearer {raw_key}"}
    first = events_client.get(
        "/public/v1/projects/general/events?limit=2", headers=headers
    )
    assert first.status_code == 200
    body = first.json()
    assert [item["run"]["id"] for item in body["items"]] == ["run-0", "run-1"]
    assert body["retention_days"] == 90
    assert body["next_cursor"] == body["items"][-1]["cursor"]

    second = events_client.get(
        f"/public/v1/projects/general/events?cursor={body['next_cursor']}",
        headers=headers,
    )
    assert second.status_code == 200
    assert [item["run"]["id"] for item in second.json()["items"]] == ["run-2"]


def test_event_feed_excludes_test_events_and_filters_by_flow(
    events_client: TestClient,
) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        session.add(
            AgateGraph(
                id="graph-other-flow",
                name="Other flow",
                spec_json=GraphSpec(name="o", nodes=[], edges=[]).model_dump_json(),
                project_id=1,
            )
        )
        session.commit()
        _seed_event(session, run_id="run-main")
        _seed_event(session, graph_id="graph-other-flow", run_id="run-other")
        _seed_event(session, run_id="run-test", is_test=True)

    headers = {"Authorization": f"Bearer {raw_key}"}
    everything = events_client.get(
        "/public/v1/projects/general/events", headers=headers
    ).json()
    assert [item["run"]["id"] for item in everything["items"]] == [
        "run-main",
        "run-other",
    ]

    filtered = events_client.get(
        "/public/v1/projects/general/events?flow_id=graph-other-flow",
        headers=headers,
    ).json()
    assert [item["run"]["id"] for item in filtered["items"]] == ["run-other"]


def test_event_feed_expired_cursor_returns_410(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    expired = encode_event_cursor(
        sequence=1,
        created_at=datetime.now(UTC) - timedelta(days=120),
    )
    response = events_client.get(
        f"/public/v1/projects/general/events?cursor={expired}",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "cursor_expired"


def test_event_feed_rejects_malformed_cursor(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    response = events_client.get(
        "/public/v1/projects/general/events?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 400


def _seed_run_with_articles(session: Session) -> str:
    run = AgateRun(graph_id="graph-events-flow", status="succeeded", execution_attempt=2)
    session.add(run)
    session.flush()
    for attempt, headline in ((1, "First attempt article"), (2, "Second attempt article")):
        article = SubstrateArticle(
            project_id=1,
            headline=headline,
            text=f"Body for {headline}",
            url=f"https://example.com/{attempt}",
        )
        session.add(article)
        session.flush()
        session.add(
            AgateRunOutputArticle(
                run_id=run.id,
                execution_attempt=attempt,
                article_id=int(article.id),
            )
        )
    session.commit()
    return str(run.id)


def test_run_articles_defaults_to_latest_attempt(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        run_id = _seed_run_with_articles(session)

    response = events_client.get(
        f"/public/v1/projects/general/runs/{run_id}/articles",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attempt"] == 2
    assert body["latest_attempt"] == 2
    assert [item["headline"] for item in body["items"]] == ["Second attempt article"]
    assert body["pagination"]["total"] == 1


def test_run_articles_attempt_history_is_immutable(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        run_id = _seed_run_with_articles(session)

    response = events_client.get(
        f"/public/v1/projects/general/runs/{run_id}/articles?attempt=1",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attempt"] == 1
    assert [item["headline"] for item in body["items"]] == ["First attempt article"]


def test_run_articles_unknown_attempt_404(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        run_id = _seed_run_with_articles(session)

    response = events_client.get(
        f"/public/v1/projects/general/runs/{run_id}/articles?attempt=5",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 404


def test_run_articles_skips_deleted_articles(events_client: TestClient) -> None:
    raw_key = _read_key(events_client)
    with Session(events_client.test_engine) as session:  # type: ignore[attr-defined]
        run_id = _seed_run_with_articles(session)
        row = session.exec(
            select(SubstrateArticle).where(
                SubstrateArticle.headline == "Second attempt article"
            )
        ).one()
        row.deleted = True
        session.add(row)
        session.commit()

    response = events_client.get(
        f"/public/v1/projects/general/runs/{run_id}/articles",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200
    body = response.json()
    # The association row still counts toward the snapshot, but the deleted
    # article body is no longer exposed.
    assert body["pagination"]["total"] == 1
    assert body["items"] == []
