"""Tests for project-scoped processed-item list and search."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from api.deps import get_session
from api.main import app
from api.project_processed_items import _keys_cte, resolve_project_item_title_and_url
from backfield_db import (
    AgateProcessedItem,
    BackfieldOrganization,
    SubstrateArticle,
)
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, SQLModel, create_engine, select

from tests.agate_api.test_agate_api import _insert_pending_run, _post_project
from tests.integration_helpers import patch_test_engine


@pytest.fixture
def client_and_engine(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, object], None, None]:
    database_path = tmp_path / "agate-project-items.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    patch_test_engine(monkeypatch, engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield (
            TestClient(
                app,
                headers={
                    "Authorization": "Bearer backfield-dev",
                    "X-Backfield-Organization-ID": "1",
                },
            ),
            engine,
        )
    finally:
        app.dependency_overrides.clear()


def test_resolve_title_prefers_article_headline_over_generic() -> None:
    title, url = resolve_project_item_title_and_url(
        item_id=1,
        source_file="batch/story.json",
        input_json='{"headline":"From input","url":"https://example.com/from-input"}',
        article_headline="City council votes",
        article_url="https://example.com/council",
    )
    assert title == "City council votes"
    assert url == "https://example.com/council"


def test_resolve_title_skips_generic_article_headline() -> None:
    title, url = resolve_project_item_title_and_url(
        item_id=2,
        source_file="path/to/file.json",
        input_json='{"headline":"Real headline"}',
        article_headline="article",
        article_url=None,
    )
    assert title == "Real headline"
    assert url is None


def test_resolve_title_falls_back_to_source_file() -> None:
    title, url = resolve_project_item_title_and_url(
        item_id=3,
        source_file="s3://bucket/path/story-abc.json",
        input_json='{"text":"long body without a headline"}',
        article_headline=None,
        article_url=None,
    )
    assert title == "story-abc.json"
    assert url is None


def test_story_keys_cte_materializes_on_postgresql() -> None:
    """Postgres compile must emit AS MATERIALIZED without cte(materialized=...)."""
    engine = create_engine("postgresql+psycopg://")
    with Session(engine) as session:
        for query in (None, "white sox"):
            keys = _keys_cte(session, 1, query)
            compiled = str(select(keys).compile(dialect=postgresql.dialect()))
            assert "project_item_keys AS MATERIALIZED" in compiled


def test_list_project_processed_items_recent_and_search(
    client_and_engine: tuple[TestClient, object],
) -> None:
    client, engine = client_and_engine

    project_a = _post_project(client, name="Articles A", slug="articles-a").json()
    project_b = _post_project(client, name="Articles B", slug="articles-b").json()

    graph_a = client.post(
        "/graphs",
        json={
            "name": "Ingest flow",
            "project_id": project_a["id"],
            "spec": {"name": "ingest", "nodes": [], "edges": []},
        },
    ).json()
    graph_b = client.post(
        "/graphs",
        json={
            "name": "Other project flow",
            "project_id": project_b["id"],
            "spec": {"name": "other", "nodes": [], "edges": []},
        },
    ).json()

    older = datetime.now(UTC) - timedelta(hours=2)
    newer = datetime.now(UTC) - timedelta(minutes=5)

    with Session(engine) as s:
        run_a = _insert_pending_run(s, graph_a["id"])
        run_b = _insert_pending_run(s, graph_b["id"])
        run_a.status = "succeeded"
        run_b.status = "succeeded"
        s.add(run_a)
        s.add(run_b)
        s.flush()

        article = SubstrateArticle(
            project_id=project_a["id"],
            headline="Council approves budget",
            text="Body text that should never match search alone xyzuniquebody",
            url="https://news.example.com/budget",
        )
        s.add(article)
        s.flush()

        linked = AgateProcessedItem(
            run_id=run_a.id,
            source_file="batch/budget.json",
            input_json='{"text":"ignored body"}',
            status="succeeded",
            result_json="{}",
            substrate_article_id=article.id,
            created_at=newer,
        )
        orphan = AgateProcessedItem(
            run_id=run_a.id,
            source_file="feeds/orphan-story.json",
            input_json='{"headline":"Orphan headline only","url":"https://news.example.com/orphan"}',
            status="failed",
            error_message="boom",
            created_at=older,
        )
        other = AgateProcessedItem(
            run_id=run_b.id,
            source_file="other.json",
            input_json='{"headline":"Council approves budget"}',
            status="succeeded",
            result_json="{}",
            created_at=newer,
        )
        s.add(linked)
        s.add(orphan)
        s.add(other)
        s.commit()
        linked_id = linked.id
        orphan_id = orphan.id
        run_a_id = run_a.id
        article_id = article.id

    empty = client.get(f"/projects/{project_a['id']}/processed-items")
    assert empty.status_code == 200
    body = empty.json()
    assert body["total"] == 2
    assert body["q"] is None
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == linked_id
    assert body["items"][0]["title"] == "Council approves budget"
    assert body["items"][0]["url"] == "https://news.example.com/budget"
    assert body["items"][0]["flow_name"] == "Ingest flow"
    assert body["items"][0]["run_id"] == run_a_id
    assert body["items"][0]["processing_count"] == 1
    assert body["items"][0]["article_id"] == article_id
    assert body["items"][1]["id"] == orphan_id
    assert body["items"][1]["title"] == "Orphan headline only"
    assert body["items"][1]["processing_count"] == 1
    assert body["items"][1]["article_id"] is None

    by_headline = client.get(
        f"/projects/{project_a['id']}/processed-items",
        params={"q": "Council approves"},
    )
    assert by_headline.status_code == 200
    hits = by_headline.json()
    assert hits["total"] == 1
    assert hits["q"] == "Council approves"
    assert hits["items"][0]["id"] == linked_id

    by_url = client.get(
        f"/projects/{project_a['id']}/processed-items",
        params={"q": "news.example.com/budget"},
    )
    assert by_url.status_code == 200
    assert by_url.json()["total"] == 1
    assert by_url.json()["items"][0]["id"] == linked_id

    by_source = client.get(
        f"/projects/{project_a['id']}/processed-items",
        params={"q": "orphan-story"},
    )
    assert by_source.status_code == 200
    assert by_source.json()["total"] == 1
    assert by_source.json()["items"][0]["id"] == orphan_id

    # Body-only unique token must not match (headline/URL/source only).
    by_body = client.get(
        f"/projects/{project_a['id']}/processed-items",
        params={"q": "xyzuniquebody"},
    )
    assert by_body.status_code == 200
    assert by_body.json()["total"] == 0

    page = client.get(
        f"/projects/{project_a['id']}/processed-items",
        params={"limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    page_body = page.json()
    assert page_body["total"] == 2
    assert page_body["limit"] == 1
    assert page_body["offset"] == 1
    assert len(page_body["items"]) == 1
    assert page_body["items"][0]["id"] == orphan_id

    # Other project's item is excluded even when headline matches.
    other_list = client.get(f"/projects/{project_b['id']}/processed-items")
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 1


def test_list_project_processed_items_groups_repeat_processings(
    client_and_engine: tuple[TestClient, object],
) -> None:
    client, engine = client_and_engine
    project = _post_project(client, name="Grouped", slug="grouped-articles").json()
    newer_flow = client.post(
        "/graphs",
        json={
            "name": "Newer flow",
            "project_id": project["id"],
            "spec": {"name": "newer", "nodes": [], "edges": []},
        },
    ).json()
    older_flow = client.post(
        "/graphs",
        json={
            "name": "Older flow",
            "project_id": project["id"],
            "spec": {"name": "older", "nodes": [], "edges": []},
        },
    ).json()

    older = datetime.now(UTC) - timedelta(hours=3)
    middle = datetime.now(UTC) - timedelta(hours=1)
    newer = datetime.now(UTC) - timedelta(minutes=5)
    story_url = "https://news.example.com/Braden-Story"

    with Session(engine) as s:
        older_run = _insert_pending_run(s, older_flow["id"])
        newer_run = _insert_pending_run(s, newer_flow["id"])
        other_run = _insert_pending_run(s, newer_flow["id"])
        for run in (older_run, newer_run, other_run):
            run.status = "succeeded"
            s.add(run)
        s.flush()

        article = SubstrateArticle(
            project_id=project["id"],
            headline="Current headline",
            text="Body that must not be required for grouping",
            url=story_url,
        )
        other_article = SubstrateArticle(
            project_id=project["id"],
            headline="Different story",
            text="Other body",
            url="https://news.example.com/other",
        )
        s.add(article)
        s.add(other_article)
        s.flush()

        older_item = AgateProcessedItem(
            run_id=older_run.id,
            source_file="batch/old.json",
            input_json='{"headline":"Old searchable headline","url":"https://news.example.com/braden-story"}',
            status="succeeded",
            result_json="{}",
            substrate_article_id=article.id,
            created_at=older,
        )
        unlinked_same_url = AgateProcessedItem(
            run_id=older_run.id,
            source_file="batch/unlinked.json",
            input_json=f'{{"headline":"From the file","url":"{story_url}"}}',
            status="failed",
            error_message="before persist",
            created_at=middle,
        )
        newer_item = AgateProcessedItem(
            run_id=newer_run.id,
            source_file="batch/new.json",
            input_json='{"headline":"Current headline"}',
            status="failed",
            error_message="latest failed",
            substrate_article_id=article.id,
            created_at=newer,
        )
        other_item = AgateProcessedItem(
            run_id=other_run.id,
            source_file="batch/other.json",
            input_json='{"headline":"Different story"}',
            status="succeeded",
            result_json="{}",
            substrate_article_id=other_article.id,
            created_at=middle,
        )
        url_only_older = AgateProcessedItem(
            run_id=older_run.id,
            source_file="batch/url-old.json",
            input_json='{"headline":"URL only old","url":"https://Example.com/URL-Only"}',
            status="succeeded",
            result_json="{}",
            created_at=older,
        )
        url_only_newer = AgateProcessedItem(
            run_id=newer_run.id,
            source_file="batch/url-new.json",
            input_json='{"headline":"URL only new","url":"https://example.com/url-only"}',
            status="succeeded",
            result_json="{}",
            created_at=newer,
        )
        s.add(older_item)
        s.add(unlinked_same_url)
        s.add(newer_item)
        s.add(other_item)
        s.add(url_only_older)
        s.add(url_only_newer)
        s.commit()
        article_id = int(article.id)
        newer_item_id = int(newer_item.id)
        older_item_id = int(older_item.id)
        unlinked_id = int(unlinked_same_url.id)
        other_item_id = int(other_item.id)
        url_only_newer_id = int(url_only_newer.id)
        url_only_older_id = int(url_only_older.id)

    listed = client.get(f"/projects/{project['id']}/processed-items")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 3
    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == {newer_item_id, other_item_id, url_only_newer_id}
    story = by_id[newer_item_id]
    assert story["processing_count"] == 3
    assert story["article_id"] == article_id
    assert story["status"] == "failed"
    assert story["flow_name"] == "Newer flow"
    assert story["title"] == "Current headline"
    assert by_id[other_item_id]["processing_count"] == 1
    assert by_id[url_only_newer_id]["processing_count"] == 2
    assert by_id[url_only_newer_id]["article_id"] is None
    assert by_id[url_only_newer_id]["title"] == "URL only new"

    # A hit on an older processing still returns the newest row for that story.
    found = client.get(
        f"/projects/{project['id']}/processed-items",
        params={"q": "Old searchable"},
    )
    assert found.status_code == 200
    found_body = found.json()
    assert found_body["total"] == 1
    assert found_body["items"][0]["id"] == newer_item_id
    assert found_body["items"][0]["processing_count"] == 3

    history = client.get(
        f"/projects/{project['id']}/processed-items",
        params={"article_id": article_id},
    )
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["total"] == 3
    assert [item["id"] for item in history_body["items"]] == [
        newer_item_id,
        unlinked_id,
        older_item_id,
    ]
    assert [item["processing_count"] for item in history_body["items"]] == [1, 1, 1]

    url_history = client.get(
        f"/projects/{project['id']}/processed-items",
        params={"url": "https://example.com/url-only"},
    )
    assert url_history.status_code == 200
    url_body = url_history.json()
    assert url_body["total"] == 2
    assert [item["id"] for item in url_body["items"]] == [url_only_newer_id, url_only_older_id]


def test_list_project_processed_items_requires_access(
    client_and_engine: tuple[TestClient, object],
) -> None:
    client, _engine = client_and_engine
    project = _post_project(client, name="Locked", slug="locked-items").json()
    resp = client.get(
        f"/projects/{project['id']}/processed-items",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code in (401, 403)


def test_list_project_processed_items_404(
    client_and_engine: tuple[TestClient, object],
) -> None:
    client, _engine = client_and_engine
    assert client.get("/projects/999999/processed-items").status_code == 404
