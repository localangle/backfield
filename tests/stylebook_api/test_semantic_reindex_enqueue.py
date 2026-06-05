"""Stylebook API tests for semantic re-index enqueue."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backfield_db import BackfieldProject, SubstrateArticle, SubstratePerson, SubstratePersonMention
from backfield_entities.ingest.semantic_indexing.reindex_contract import SEMANTIC_REINDEX_TASK_NAME
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from tests.stylebook_api.test_stylebook_api import _service_headers

pytest_plugins = ["tests.stylebook_api.test_stylebook_api"]


def _demo_project_id(session: Session) -> int:
    proj = session.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
    return int(proj.id)


def test_patch_person_sort_key_only_does_not_enqueue_reindex(
    _stylebook_test_stack: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = _stylebook_test_stack
    send_task = MagicMock()
    monkeypatch.setattr("stylebook_api.semantic_reindex.celery_app.send_task", send_task)

    with Session(engine) as session:
        project_id = _demo_project_id(session)
        article = SubstrateArticle(project_id=project_id, headline="H", text="Body")
        session.add(article)
        session.commit()
        session.refresh(article)
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Smith",
            normalized_name="jane smith",
            identity_fingerprint="fp-reindex-sort-key",
            status="active",
            sort_key="jane-smith",
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        session.add(
            SubstratePersonMention(
                article_id=int(article.id),
                person_id=int(person.id),
                source_kind="manual_add",
            )
        )
        session.commit()
        person_id = int(person.id)
        article_id = int(article.id)

    resp = client.patch(
        f"/v1/people/{person_id}?project_slug=demo-proj&article_id={article_id}",
        headers=_service_headers(),
        json={"sort_key": "smith-j"},
    )
    assert resp.status_code == 200
    send_task.assert_not_called()


def test_patch_person_name_enqueues_reindex(
    _stylebook_test_stack: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = _stylebook_test_stack
    send_task = MagicMock()
    monkeypatch.setattr("stylebook_api.semantic_reindex.celery_app.send_task", send_task)

    with Session(engine) as session:
        project_id = _demo_project_id(session)
        article = SubstrateArticle(project_id=project_id, headline="H", text="Body")
        session.add(article)
        session.commit()
        session.refresh(article)
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Smith",
            normalized_name="jane smith",
            identity_fingerprint="fp-reindex-name",
            status="active",
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        session.add(
            SubstratePersonMention(
                article_id=int(article.id),
                person_id=int(person.id),
                source_kind="manual_add",
            )
        )
        session.commit()
        person_id = int(person.id)
        article_id = int(article.id)
        saved_project_id = project_id

    resp = client.patch(
        f"/v1/people/{person_id}?project_slug=demo-proj&article_id={article_id}",
        headers=_service_headers(),
        json={"name": "Jane Q Smith"},
    )
    assert resp.status_code == 200
    send_task.assert_called_once_with(
        SEMANTIC_REINDEX_TASK_NAME,
        args=[saved_project_id, article_id, "person"],
        queue="agate",
    )
