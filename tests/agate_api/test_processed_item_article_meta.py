"""Processed-item article metadata review API."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from api.deps import get_session
from api.main import app
from api.routers import runs
from backfield_db import (
    AgateProcessedItem,
    BackfieldOrganization,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.agate_api.test_agate_api import _insert_pending_run, _minimal_text_input_spec


def _seed_article_with_meta(session: Session, *, project_id: int) -> tuple[int, int]:
    article = SubstrateArticle(
        project_id=project_id,
        headline="Headline",
        text="Body",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    meta = SubstrateArticleMeta(
        article_id=int(article.id),  # type: ignore[arg-type]
        meta_type="subject",
        category="Local news",
        rationale="Because",
        confidence=0.82,
        prompt_preset="subject",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(meta)
    session.commit()
    session.refresh(meta)
    return int(article.id), int(meta.id)  # type: ignore[arg-type]


def test_get_processed_item_includes_article_meta_rows(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "agate-meta-get.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(BackfieldOrganization(name="Backfield", slug="default"))
        session.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Meta Get", "slug": "meta-get-api"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="meta-get"),
            },
        ).json()
        with Session(engine) as session:
            article_id, _meta_id = _seed_article_with_meta(
                session,
                project_id=int(project["id"]),
            )
            run_row = _insert_pending_run(session, graph["id"])
            rid = run_row.id
            run_row.status = "succeeded"
            session.add(run_row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="x.json",
                input_json="{}",
                status="succeeded",
                result_json=(
                    '{"stylebook_output":{"article_id":'
                    f"{article_id},"
                    '"article_metadata":{"meta_type":"subject","category":"Local news",'
                    '"rationale":"Because","confidence":0.82}}}'
                ),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            iid = item.id

        response = tc.get(f"/runs/{rid}/items/{iid}")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["article_meta"]) == 1
        assert payload["article_meta"][0]["category"] == "Local news"
        assert payload["article_meta"][0]["meta_type"] == "subject"
    finally:
        app.dependency_overrides.clear()


def test_patch_article_meta_category_updates_substrate_and_overlay(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "agate-meta-patch.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(BackfieldOrganization(name="Backfield", slug="default"))
        session.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Meta Patch", "slug": "meta-patch-api"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="meta-patch"),
            },
        ).json()
        with Session(engine) as session:
            article_id, meta_id = _seed_article_with_meta(
                session,
                project_id=int(project["id"]),
            )
            run_row = _insert_pending_run(session, graph["id"])
            rid = run_row.id
            run_row.status = "succeeded"
            session.add(run_row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="x.json",
                input_json="{}",
                status="succeeded",
                result_json=(
                    '{"stylebook_output":{"article_id":'
                    f"{article_id},"
                    '"article_metadata":{"meta_type":"subject","category":"Local news",'
                    '"rationale":"Because","confidence":0.82}}}'
                ),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            iid = item.id

        response = tc.patch(
            f"/runs/{rid}/items/{iid}/article-meta/{meta_id}",
            json={"category": "Politics"},
            headers={"If-Match": '"0"'},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["article_meta"][0]["category"] == "Politics"
        assert payload["article_meta"][0]["source"] == "review"
        assert payload["overlay_version"] == 1
        reviewed = payload["reviewed_output"]
        assert reviewed["stylebook_output"]["article_metadata"]["category"] == "Politics"

        with Session(engine) as session:
            row = session.get(SubstrateArticleMeta, meta_id)
            assert row is not None
            assert row.category == "Politics"
    finally:
        app.dependency_overrides.clear()


def test_patch_article_meta_category_overlay_only_json_output(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "agate-meta-overlay.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(BackfieldOrganization(name="Backfield", slug="default"))
        session.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post(
            "/projects",
            json={"name": "Meta Overlay", "slug": "meta-overlay-api"},
        ).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="meta-overlay"),
            },
        ).json()
        with Session(engine) as session:
            run_row = _insert_pending_run(session, graph["id"])
            rid = run_row.id
            run_row.status = "succeeded"
            session.add(run_row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="x.json",
                input_json='{"headline":"Story","text":"Body"}',
                status="succeeded",
                result_json=(
                    '{"json_output":{"consolidated":{"headline":"Story","text":"Body",'
                    '"article_metadata":{"meta_type":"subject","category":"Local news",'
                    '"rationale":"Because","confidence":0.82}}}}'
                ),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            iid = item.id

        detail = tc.get(f"/runs/{rid}/items/{iid}").json()
        synthetic_id = detail["article_meta"][0]["id"]
        assert synthetic_id < 0

        response = tc.patch(
            f"/runs/{rid}/items/{iid}/article-meta/{synthetic_id}",
            json={"category": "Politics"},
            headers={"If-Match": '"0"'},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["article_meta"][0]["category"] == "Politics"
        assert payload["article_meta"][0]["source"] == "review"
        reviewed = payload["reviewed_output"]
        assert reviewed["json_output"]["consolidated"]["article_metadata"]["category"] == "Politics"
    finally:
        app.dependency_overrides.clear()
