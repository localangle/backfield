"""API tests for semantic mention search endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backfield_ai.query_embedding import SemanticQueryEmbedding
from backfield_db import BackfieldProject
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from tests.entities.test_semantic_mention_search_fixtures import (
    seed_person_semantic_search_rows,
    set_person_semantic_doc_embedding,
)
from tests.stylebook_api.test_stylebook_api import _service_headers

pytest_plugins = ["tests.stylebook_api.test_stylebook_api"]


def _demo_project_id(session: Session) -> int:
    proj = session.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
    return int(proj.id)


def _seed_demo_person_search(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        ids = seed_person_semantic_search_rows(session, project_id=_demo_project_id(session))
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["ready_doc_id"],
            vector=[1.0, 0.0],
        )
        session.commit()
        return ids


@patch("stylebook_api.routers.semantic_mention_search.embed_semantic_search_query")
def test_person_semantic_mention_search_returns_evidence_rows(
    mock_embed: MagicMock,
    _stylebook_test_stack: tuple[TestClient, Engine],
) -> None:
    client, engine = _stylebook_test_stack
    ids = _seed_demo_person_search(engine)
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )

    resp = client.post(
        "/v1/people/semantic-mentions/search?project_slug=demo-proj",
        headers=_service_headers(),
        json={"query": "downtown crime"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["embedding_model"] == "openai/text-embedding-3-small"
    assert body["results"][0]["entity_type"] == "person"
    assert body["results"][0]["article"]["id"] == ids["article_id"]
    assert body["results"][0]["occurrence"]["mention_text"]


@patch("stylebook_api.routers.semantic_mention_search.embed_semantic_search_query")
def test_person_semantic_mention_search_nature_filter(
    mock_embed: MagicMock,
    _stylebook_test_stack: tuple[TestClient, Engine],
) -> None:
    client, engine = _stylebook_test_stack
    _seed_demo_person_search(engine)
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )

    resp = client.post(
        "/v1/people/semantic-mentions/search?project_slug=demo-proj",
        headers=_service_headers(),
        json={"query": "downtown crime", "nature": "official"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    miss = client.post(
        "/v1/people/semantic-mentions/search?project_slug=demo-proj",
        headers=_service_headers(),
        json={"query": "downtown crime", "nature": "witness"},
    )
    assert miss.status_code == 200
    assert miss.json()["total"] == 0


@patch("stylebook_api.routers.semantic_mention_search.embed_semantic_search_query")
def test_location_semantic_mention_search_empty_without_rows(
    mock_embed: MagicMock,
    _stylebook_test_stack: tuple[TestClient, Engine],
) -> None:
    client, _engine = _stylebook_test_stack
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )

    resp = client.post(
        "/v1/locations/semantic-mentions/search?project_slug=demo-proj",
        headers=_service_headers(),
        json={"query": "city hall"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["results"] == []
