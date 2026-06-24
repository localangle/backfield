"""Tests for Core API `/public/v1` routes."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.query_embedding import SemanticQueryEmbedding
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookConnection,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateArticleEmbedding,
    SubstrateArticleMeta,
    SubstrateCustomRecord,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.geo.h3_index import derive_h3_index
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def public_client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "public-api-test.db"
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
        sb_id = int(sb.id)  # type: ignore[arg-type]
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name="Default Workspace",
            slug="default",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        s.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=oid,
                workspace_id=int(ws.id),
            )
        )
        s.add(
            BackfieldProject(
                name="Other",
                slug="other",
                organization_id=oid,
                workspace_id=int(ws.id),
            )
        )
        s.commit()
        general = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "general")).one()
        article = SubstrateArticle(
            project_id=int(general.id),  # type: ignore[arg-type]
            headline="City council votes on budget",
            url="https://example.com/budget",
            author="Jane Doe",
            pub_date=date(2024, 3, 1),
            text="The council approved the budget after a long debate downtown.",
        )
        s.add(article)
        s.commit()
        s.refresh(article)
        s.add(
            SubstrateArticleMeta(
                article_id=int(article.id),  # type: ignore[arg-type]
                meta_type="topic",
                category="local_government_politics",
                rationale="Classified during ingest.",
                confidence=0.92,
            )
        )
        project_id = int(general.id)  # type: ignore[arg-type]
        article_id = int(article.id)  # type: ignore[arg-type]
        s.add(
            SubstrateArticleEmbedding(
                article_id=article_id,
                embedded_text="City council budget story",
                embedding_model="text-embedding-3-small",
                embedding_dimensions=2,
                embedding_ai_model_config_id="emb-test",
                embedding=json.dumps([1.0, 0.0]),
            )
        )
        location = SubstrateLocation(
            project_id=project_id,
            name="City Hall",
            normalized_name="city hall",
            location_type="place",
            formatted_address="123 Main St",
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
        )
        derived_h3 = derive_h3_index(location.geometry_json)
        if derived_h3 is not None:
            location.h3_cell = derived_h3.h3_cell
            location.h3_resolution = derived_h3.h3_resolution
        s.add(location)
        s.commit()
        s.refresh(location)
        location_canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="City Hall",
            slug="city-hall",
            location_type="place",
            formatted_address="123 Main St",
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
        )
        s.add(location_canon)
        s.commit()
        s.refresh(location_canon)
        location.stylebook_location_canonical_id = str(location_canon.id)
        s.add(location)
        s.commit()
        location_mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=int(location.id),  # type: ignore[arg-type]
            nature="primary",
        )
        s.add(location_mention)
        s.commit()
        s.refresh(location_mention)
        s.add(
            SubstrateLocationMentionOccurrence(
                location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
                mention_text="City Hall",
                quote_text="debate downtown",
                start_char=40,
                end_char=55,
            )
        )
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Doe",
            normalized_name="jane doe",
        )
        s.add(person)
        s.commit()
        s.refresh(person)
        person_canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
            title="Mayor",
            affiliation="City Hall",
            person_type="elected_official",
            public_figure=True,
        )
        s.add(person_canon)
        s.commit()
        s.refresh(person_canon)
        person.stylebook_person_canonical_id = str(person_canon.id)
        s.add(person)
        s.commit()
        person_mention = SubstratePersonMention(
            article_id=article_id,
            person_id=int(person.id),  # type: ignore[arg-type]
            nature="subject",
        )
        s.add(person_mention)
        s.commit()
        s.refresh(person_mention)
        s.add(
            SubstratePersonMentionOccurrence(
                person_mention_id=int(person_mention.id),  # type: ignore[arg-type]
                mention_text="Jane Doe",
            )
        )
        s.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=str(person_canon.id),
                to_entity_type="location",
                to_entity_id=str(location_canon.id),
                nature="works_at",
            )
        )
        organization = SubstrateOrganization(
            project_id=project_id,
            name="City Council",
            normalized_name="city council",
        )
        s.add(organization)
        s.commit()
        s.refresh(organization)
        org_canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="City Council",
            slug="city-council",
            organization_type="government",
        )
        s.add(org_canon)
        s.commit()
        s.refresh(org_canon)
        organization.stylebook_organization_canonical_id = str(org_canon.id)
        s.add(organization)
        s.commit()
        s.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="organization",
                from_entity_id=str(org_canon.id),
                to_entity_type="person",
                to_entity_id=str(person_canon.id),
                nature="employs",
            )
        )
        organization_mention = SubstrateOrganizationMention(
            article_id=article_id,
            organization_id=int(organization.id),  # type: ignore[arg-type]
            nature="actor",
        )
        s.add(organization_mention)
        s.commit()
        s.refresh(organization_mention)
        s.add(
            SubstrateOrganizationMentionOccurrence(
                organization_mention_id=int(organization_mention.id),  # type: ignore[arg-type]
                mention_text="City Council",
            )
        )
        s.add(
            SubstrateImage(
                article_id=article_id,
                image_id="img-1",
                url="https://example.com/photo.jpg",
                caption="Council chamber",
            )
        )
        s.add(
            SubstrateCustomRecord(
                article_id=article_id,
                record_type="contracts",
                record_index=0,
                fields_json={"vendor": "Acme"},
                mentions_json=[],
                field_schema_json=[{"name": "vendor", "field_type": "string"}],
            )
        )
        s.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Other headline",
                text="Other body",
                pub_date=date(2023, 12, 1),
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_project_api_key(client: TestClient, project_id: int = 1) -> str:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "pub@example.com", "password": "pub-secret-12"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "pub@example.com", "password": "pub-secret-12"},
    )
    created = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"credential_type": "user", "label": "public-api"},
    )
    assert created.status_code == 200
    return str(created.json()["raw_key"])


def test_public_project_requires_api_key(public_client: TestClient) -> None:
    r = public_client.get("/public/v1/projects/general")
    assert r.status_code == 401


def test_public_project_rejects_session_cookie(public_client: TestClient) -> None:
    public_client.post(
        "/v1/bootstrap/first-user",
        json={"email": "sesspub@example.com", "password": "sesspub-secret-12"},
    )
    public_client.post(
        "/v1/auth/login",
        json={"email": "sesspub@example.com", "password": "sesspub-secret-12"},
    )
    r = public_client.get("/public/v1/projects/general")
    assert r.status_code == 401


def test_public_project_metadata(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    r = public_client.get(
        "/public/v1/projects/general",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "general"
    assert body["name"] == "General"
    assert body["id"] == 1
    assert body["stylebook_slug"] == "default"
    assert body["stylebook_name"]
    assert body["stats"] == {
        "articles": {"total": 2, "embedded": 1},
        "mentions": {"total": 3, "embedded": 0},
        "images": {"total": 1, "embedded": 0},
    }


def test_public_project_unknown_slug(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    r = public_client.get(
        "/public/v1/projects/no-such-project",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 404


def test_public_project_wrong_project_key(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client, project_id=1)
    r = public_client.get(
        "/public/v1/projects/other",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 403


def test_public_project_service_token(public_client: TestClient) -> None:
    r = public_client.get(
        "/public/v1/projects/general",
        headers={"Authorization": "Bearer backfield-dev"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "general"


def test_public_article_search(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get("/public/v1/projects/general/articles/search", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 2
    headlines = {item["headline"] for item in body["items"]}
    assert "City council votes on budget" in headlines


def test_public_article_search_body_keyword(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "downtown"},
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 1
    assert r.json()["items"][0]["headline"] == "City council votes on budget"


@patch("core_api.routers.public.articles.semantic_search.embed_semantic_search_query")
def test_public_article_semantic_search(
    mock_embed: MagicMock,
    public_client: TestClient,
) -> None:
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.post(
        "/public/v1/projects/general/articles/semantic-search",
        headers=headers,
        json={"query": "city budget debate"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["embedding_model_config_id"] == "emb-test"
    assert body["pagination"]["total"] == 1
    item = body["items"][0]
    assert item["headline"] == "City council votes on budget"
    assert item["score"] > 0
    assert item["preview"]
    assert item["metadata"]
    assert item.get("counts") is None
    assert item.get("embedded") is None


@patch("core_api.routers.public.articles.semantic_search.embed_semantic_search_query")
def test_public_article_semantic_search_include_counts(
    mock_embed: MagicMock,
    public_client: TestClient,
) -> None:
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.post(
        "/public/v1/projects/general/articles/semantic-search",
        headers=headers,
        json={"query": "city budget debate", "include": ["counts"]},
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["embedded"] is True
    assert item["counts"]["mentions"]["total"] == 3
    assert item["counts"]["entities"]["total"] == 3
    assert item["score"] > 0


@patch("core_api.routers.public.articles.semantic_search.embed_semantic_search_query")
def test_public_article_semantic_search_with_hyde(
    mock_embed: MagicMock,
    public_client: TestClient,
) -> None:
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
        hyde_used=True,
        hypothetical_document="Council members debated the downtown budget late into the night.",
        hyde_model_config_id="gen-test",
        hyde_model="openai/gpt-4o-mini",
    )
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.post(
        "/public/v1/projects/general/articles/semantic-search",
        headers=headers,
        json={"query": "city budget debate", "use_hyde": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hyde_used"] is True
    assert body["hypothetical_document"] == (
        "Council members debated the downtown budget late into the night."
    )
    assert body["hyde_model_config_id"] == "gen-test"
    assert body["hyde_model"] == "openai/gpt-4o-mini"
    mock_embed.assert_called_once()
    assert mock_embed.call_args.kwargs["use_hyde"] is True


def test_public_article_geo_search_by_point(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params={
            "center_lng": -87.6,
            "center_lat": 41.8,
            "radius_miles": 5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["search_mode"] == "point"
    assert body["center_lng"] == -87.6
    assert body["center_lat"] == 41.8
    assert body["radius_miles"] == 5
    assert body["location_types"] == []
    assert body["items"][0]["headline"] == "City council votes on budget"
    assert len(body["items"][0]["matching_locations"]) == 1
    assert body["items"][0]["matching_locations"][0]["label"] == "City Hall"
    assert "substrate_location_id" not in body["items"][0]["matching_locations"][0]
    assert "article" not in body["items"][0]


def test_public_article_geo_cells(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={"bbox": "-88,41,-87,42"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "resolution" in body
    assert "derived_resolution" in body
    assert "bbox_extent_km" in body
    assert body["coarsened"] is False
    assert isinstance(body["cells"], list)
    assert len(body["cells"]) >= 1
    cell = body["cells"][0]
    assert "h3_cell" in cell
    assert "article_count" in cell
    assert cell["article_count"] == 1

    missing = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
    )
    assert missing.status_code == 422

    invalid = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={"bbox": "-87,42,-88,41"},
    )
    assert invalid.status_code == 400


def test_public_article_geo_cells_metadata_and_date_filters(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    matched = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={
            "bbox": "-88,41,-87,42",
            "section": "local_government_politics",
            "pub_date_from": "2024-03-01",
            "pub_date_to": "2024-03-31",
        },
    )
    assert matched.status_code == 200
    assert matched.json()["cells"][0]["article_count"] == 1

    wrong_section = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={"bbox": "-88,41,-87,42", "section": "sports"},
    )
    assert wrong_section.status_code == 200
    assert wrong_section.json()["cells"] == []

    out_of_range = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={
            "bbox": "-88,41,-87,42",
            "pub_date_from": "2025-01-01",
            "pub_date_to": "2025-12-31",
        },
    )
    assert out_of_range.status_code == 200
    assert out_of_range.json()["cells"] == []


def test_public_article_geo_cell_detail(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    coverage = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={"bbox": "-88,41,-87,42"},
    )
    assert coverage.status_code == 200
    cell_id = coverage.json()["cells"][0]["h3_cell"]

    r = public_client.get(
        f"/public/v1/projects/general/articles/geo-cells/{cell_id}",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["h3_cell"] == cell_id
    assert "resolution" in body
    assert body["pagination"]["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["article"]["headline"] == "City council votes on budget"
    assert len(body["items"][0]["matching_locations"]) == 1
    assert body["items"][0]["matching_locations"][0]["label"] == "City Hall"

    invalid = public_client.get(
        "/public/v1/projects/general/articles/geo-cells/not-a-valid-cell",
        headers=headers,
    )
    assert invalid.status_code == 400


def test_public_article_geo_cells_batch(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    coverage = public_client.get(
        "/public/v1/projects/general/articles/geo-cells",
        headers=headers,
        params={"bbox": "-88,41,-87,42"},
    )
    assert coverage.status_code == 200
    cell_id = coverage.json()["cells"][0]["h3_cell"]
    resolution = coverage.json()["resolution"]

    r = public_client.post(
        "/public/v1/projects/general/articles/geo-cells/query",
        headers=headers,
        json={
            "cells": [cell_id],
            "resolution": resolution,
            "limit": 100,
            "offset": 0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["resolution"] == resolution
    assert body["pagination"]["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["matched_cells"] == [cell_id]
    assert body["items"][0]["article"]["headline"] == "City council votes on budget"
    assert len(body["per_cell_totals"]) == 1
    assert body["per_cell_totals"][0]["h3_cell"] == cell_id
    assert body["per_cell_totals"][0]["article_count"] == 1


def test_public_article_geo_search_nature_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params={
            "center_lng": -87.6,
            "center_lat": 41.8,
            "radius_miles": 5,
            "nature": "primary",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1

    r = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params={
            "center_lng": -87.6,
            "center_lat": 41.8,
            "radius_miles": 5,
            "nature": "secondary",
        },
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 0


def test_public_article_geo_search_location_types_or(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    base = {
        "center_lng": -87.6,
        "center_lat": 41.8,
        "radius_miles": 5,
    }

    matched = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params={**base, "location_type": "place"},
    )
    assert matched.status_code == 200
    body = matched.json()
    assert body["location_types"] == ["place"]
    assert body["pagination"]["total"] == 1

    no_match = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params={**base, "location_type": "address"},
    )
    assert no_match.status_code == 200
    assert no_match.json()["location_types"] == ["address"]
    assert no_match.json()["pagination"]["total"] == 0

    either = public_client.get(
        "/public/v1/projects/general/articles/geo-search",
        headers=headers,
        params=[(k, v) for k, v in base.items()]
        + [("location_type", "place"), ("location_type", "address")],
    )
    assert either.status_code == 200
    assert either.json()["location_types"] == ["place", "address"]
    assert either.json()["pagination"]["total"] == 1


def test_public_article_search_keyword(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 1
    assert r.json()["q"] == "budget"
    assert r.json()["items"][0]["headline"] == "City council votes on budget"


def test_public_article_search_metadata_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={
            "meta_type": "topic",
            "meta_category": "local_government_politics",
        },
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 1


def test_public_article_search_exclude_metadata_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={
            "meta_type": "topic",
            "exclude_meta_type": "topic",
            "exclude_meta_category": "sports",
        },
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 1

    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"exclude_meta_type": "topic"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["headline"] == "Other headline"


def test_public_article_metadata_endpoints(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    types = public_client.get(
        "/public/v1/projects/general/articles/metadata/types",
        headers=headers,
    )
    assert types.status_code == 200
    assert types.json()["meta_types"] == ["topic"]

    values = public_client.get(
        "/public/v1/projects/general/articles/metadata/types/topic/values",
        headers=headers,
    )
    assert values.status_code == 200
    assert values.json() == {
        "meta_type": "topic",
        "values": ["local_government_politics"],
    }

    listed = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    ).json()
    article_id = listed["items"][0]["id"]

    metadata = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/metadata",
        headers=headers,
    )
    assert metadata.status_code == 200
    body = metadata.json()
    assert body["article_id"] == article_id
    assert body["meta_types"] == ["topic"]
    assert body["metadata"][0]["category"] == "local_government_politics"

    missing = public_client.get(
        "/public/v1/projects/general/articles/99999/metadata",
        headers=headers,
    )
    assert missing.status_code == 404


def test_public_article_search_facets_and_filters(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    facets = public_client.get(
        "/public/v1/projects/general/articles/facets",
        headers=headers,
    )
    assert facets.status_code == 200
    body = facets.json()
    assert "Jane Doe" in body["authors"]
    assert body["topic_categories"] == ["local_government_politics"]
    assert body["subject_categories"] == []

    search = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={
            "author": "Jane Doe",
            "section": "local_government_politics",
            "has_mentions": "location",
        },
    )
    assert search.status_code == 200
    item = search.json()["items"][0]
    assert item["headline"] == "City council votes on budget"
    assert item["source"]["id"] == "example.com"
    assert item["metadata"][0]["category"] == "local_government_politics"
    assert item.get("counts") is None


def test_public_article_search_invalid_date(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"pub_date_from": "not-a-date"},
    )
    assert r.status_code == 400


def test_public_article_detail(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    listed = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    ).json()
    article_id = listed["items"][0]["id"]
    r = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["headline"] == "City council votes on budget"
    assert body["author"] == "Jane Doe"
    assert "text" not in body
    assert body["preview"]
    assert body["metadata"][0]["category"] == "local_government_politics"
    assert "processing" not in body
    assert body.get("counts") is None
    assert isinstance(body["images"], list)
    assert len(body["images"]) == 1
    assert body["images"][0]["image_id"] == "img-1"


def test_public_article_detail_include_text(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    article_id = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    ).json()["items"][0]["id"]
    r = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}",
        headers=headers,
        params={"include": "text"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "text" in body
    assert body["preview"]
    assert body["text"] == (
        "The council approved the budget after a long debate downtown."
    )
    assert body.get("counts") is None


def test_public_article_search_rejects_include_text(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"include": "text"},
    )
    assert r.status_code == 400


def test_public_article_detail_include_counts(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    article_id = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    ).json()["items"][0]["id"]
    r = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}",
        headers=headers,
        params={"include": "counts"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["embedded"] is True
    assert body["counts"] == {
        "mentions": {
            "locations": 1,
            "people": 1,
            "organizations": 1,
            "total": 3,
        },
        "entities": {
            "locations": 1,
            "people": 1,
            "organizations": 1,
            "total": 3,
        },
        "images": 1,
        "custom_records": {"contracts": 1},
    }
    assert len(body["images"]) == 1


def test_public_article_search_include_counts(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget", "include": "counts"},
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["embedded"] is True
    assert item["counts"]["mentions"]["total"] == 3
    assert item["counts"]["entities"]["total"] == 3
    assert item.get("images") is None


def test_public_article_include_invalid_token(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"include": "locations"},
    )
    assert r.status_code == 400


def test_public_article_detail_not_found(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    r = public_client.get(
        "/public/v1/projects/general/articles/99999",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 404


def test_public_article_mentions(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    article_id = public_client.get(
        "/public/v1/projects/general/articles/search",
        headers=headers,
        params={"q": "budget"},
    ).json()["items"][0]["id"]
    r = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/mentions",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    types = {item["entity_type"] for item in body}
    assert types == {"location", "person", "organization"}
    assert "mention_id" not in body[0]
    assert "substrate_entity_id" not in body[0]


def test_public_article_mentions_entity_type_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    article_id = 1
    r = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/mentions",
        headers=headers,
        params={"entity_type": "location"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["label"] == "City Hall"
    assert body[0]["evidence"]["mention_text"] == "debate downtown"
    assert body[0]["evidence"]["quote"] is True
    assert "quote_text" not in body[0]["evidence"]


def test_public_article_mentions_nature_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    article_id = 1

    all_mentions = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/mentions",
        headers=headers,
    )
    assert all_mentions.status_code == 200
    assert len(all_mentions.json()) == 3

    subject_only = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/mentions",
        headers=headers,
        params={"nature": "subject"},
    )
    assert subject_only.status_code == 200
    body = subject_only.json()
    assert len(body) == 1
    assert body[0]["entity_type"] == "person"
    assert body[0]["nature"] == "subject"

    primary_location = public_client.get(
        f"/public/v1/projects/general/articles/{article_id}/mentions",
        headers=headers,
        params={"entity_type": "location", "nature": "primary"},
    )
    assert primary_location.status_code == 200
    assert len(primary_location.json()) == 1
    assert primary_location.json()[0]["nature"] == "primary"


def test_public_article_mentions_quote_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/mentions",
        headers=headers,
        params={"quote": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["entity_type"] == "location"
    assert body[0]["evidence"]["quote"] is True


def test_public_article_locations(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/locations",
        headers=headers,
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["label"] == "City Hall"
    assert item["geometry_json"]["type"] == "Point"
    assert "substrate_location_id" not in item


def test_public_article_images(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/images",
        headers=headers,
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["image_id"] == "img-1"
    assert item["caption"] == "Council chamber"


def test_public_article_people(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/people",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    person = body["items"][0]
    assert person["label"] == "Jane Doe"
    assert person["nature"] == "subject"
    assert person["canonical"]["slug"] == "jane-doe"
    assert person["canonical"]["stylebook_slug"] == "default"
    assert "substrate_person_id" not in person

    filtered = public_client.get(
        "/public/v1/projects/general/articles/1/people",
        headers=headers,
        params={"nature": "official"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] == 0


def test_public_article_organizations(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/organizations",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    org = body["items"][0]
    assert org["label"] == "City Council"
    assert org["nature"] == "actor"
    assert org["organization_type"] == "government"
    assert "substrate_organization_id" not in org


def test_public_article_custom_records(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/articles/1/custom-records",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    record = body["items"][0]
    assert record["record_type"] == "contracts"
    assert record["fields"]["vendor"] == "Acme"
    assert record["field_schema"][0]["name"] == "vendor"

    filtered = public_client.get(
        "/public/v1/projects/general/articles/1/custom-records",
        headers=headers,
        params={"record_type": "contracts"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] == 1


def test_public_people_list_and_search(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    listed = public_client.get("/public/v1/projects/general/people", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["pagination"]["total"] == 1
    person = body["items"][0]
    assert person["label"] == "Jane Doe"
    assert person["counts"]["mentions"] == 1
    assert person["stylebook_slug"] == "default"
    person_id = person["id"]

    searched = public_client.get(
        "/public/v1/projects/general/people/search",
        headers=headers,
        params={"q": "Mayor", "affiliation": "City Hall"},
    )
    assert searched.status_code == 200
    assert searched.json()["pagination"]["total"] == 1

    types = public_client.get("/public/v1/projects/general/people/types", headers=headers)
    assert types.status_code == 200
    assert "elected_official" in types.json()["types"]

    detail = public_client.get(
        f"/public/v1/projects/general/people/{person_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["title"] == "Mayor"
    assert detail.json()["stylebook_slug"] == "default"

    mentions = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
    )
    assert mentions.status_code == 200
    mbody = mentions.json()
    assert mbody["label"] == "Jane Doe"
    assert mbody["pagination"]["total"] == 1
    assert mbody["pagination"]["limit"] == 25
    assert mbody["items"][0]["article"]["headline"] == "City council votes on budget"
    assert mbody["items"][0]["nature"] == "subject"

    quoted = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
        params={"quote": "true"},
    )
    assert quoted.status_code == 200
    assert quoted.json()["pagination"]["total"] == 0

    articles = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/articles",
        headers=headers,
    )
    assert articles.status_code == 200
    abody = articles.json()
    assert abody["label"] == "Jane Doe"
    assert abody["pagination"]["total"] == 1
    assert abody["items"][0]["headline"] == "City council votes on budget"

    connections = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/connections",
        headers=headers,
    )
    assert connections.status_code == 200
    conns = connections.json()["connections"]
    assert len(conns) == 2
    assert any(c["nature"] == "works_at" for c in conns)
    assert any(c["nature"] == "employs" for c in conns)


def test_public_entity_mentions_filters(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    listed = public_client.get("/public/v1/projects/general/people", headers=headers)
    assert listed.status_code == 200
    person_id = listed.json()["items"][0]["id"]

    by_nature = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
        params={"nature": "subject"},
    )
    assert by_nature.status_code == 200
    assert by_nature.json()["pagination"]["total"] == 1

    no_nature = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
        params={"nature": "actor"},
    )
    assert no_nature.status_code == 200
    assert no_nature.json()["pagination"]["total"] == 0

    by_author = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
        params={"author": "Jane Doe"},
    )
    assert by_author.status_code == 200
    assert by_author.json()["pagination"]["total"] == 1

    default_limit = public_client.get(
        f"/public/v1/projects/general/people/{person_id}/mentions",
        headers=headers,
    )
    assert default_limit.status_code == 200
    assert default_limit.json()["pagination"]["limit"] == 25


def test_public_person_not_found(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/people/00000000-0000-4000-8000-000000009999",
        headers=headers,
    )
    assert r.status_code == 404


def test_public_organizations_list_and_search(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    listed = public_client.get("/public/v1/projects/general/organizations", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["pagination"]["total"] == 1
    organization = body["items"][0]
    assert organization["label"] == "City Council"
    assert organization["counts"]["mentions"] == 1
    organization_id = organization["id"]

    searched = public_client.get(
        "/public/v1/projects/general/organizations/search",
        headers=headers,
        params={"q": "Council", "organization_type": "government"},
    )
    assert searched.status_code == 200
    assert searched.json()["pagination"]["total"] == 1

    types = public_client.get(
        "/public/v1/projects/general/organizations/types",
        headers=headers,
    )
    assert types.status_code == 200
    assert "government" in types.json()["types"]

    detail = public_client.get(
        f"/public/v1/projects/general/organizations/{organization_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["organization_type"] == "government"

    mentions = public_client.get(
        f"/public/v1/projects/general/organizations/{organization_id}/mentions",
        headers=headers,
    )
    assert mentions.status_code == 200
    mbody = mentions.json()
    assert mbody["label"] == "City Council"
    assert mbody["pagination"]["total"] == 1
    assert mbody["items"][0]["article"]["headline"] == "City council votes on budget"
    assert mbody["items"][0]["nature"] == "actor"

    articles = public_client.get(
        f"/public/v1/projects/general/organizations/{organization_id}/articles",
        headers=headers,
    )
    assert articles.status_code == 200
    assert articles.json()["pagination"]["total"] == 1
    assert articles.json()["items"][0]["headline"] == "City council votes on budget"

    connections = public_client.get(
        f"/public/v1/projects/general/organizations/{organization_id}/connections",
        headers=headers,
    )
    assert connections.status_code == 200
    assert len(connections.json()["connections"]) == 1
    assert connections.json()["connections"][0]["nature"] == "employs"


def test_public_organization_not_found(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/organizations/00000000-0000-4000-8000-000000009999",
        headers=headers,
    )
    assert r.status_code == 404


def test_public_locations_list_search_and_geo(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    listed = public_client.get("/public/v1/projects/general/locations", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["pagination"]["total"] == 1
    location = body["items"][0]
    assert location["label"] == "City Hall"
    assert location["counts"]["mentions"] == 1
    assert location["geometry_json"]["type"] == "Point"
    location_id = location["id"]

    searched = public_client.get(
        "/public/v1/projects/general/locations/search",
        headers=headers,
        params={"q": "Main St", "location_type": "place"},
    )
    assert searched.status_code == 200
    assert searched.json()["pagination"]["total"] == 1

    geo = public_client.get(
        "/public/v1/projects/general/locations/geo-search",
        headers=headers,
        params={
            "center_lng": -87.6,
            "center_lat": 41.8,
            "radius_miles": 5,
        },
    )
    assert geo.status_code == 200
    gbody = geo.json()
    assert gbody["search_mode"] == "point"
    assert gbody["pagination"]["total"] == 1
    assert gbody["items"][0]["label"] == "City Hall"

    types = public_client.get("/public/v1/projects/general/locations/types", headers=headers)
    assert types.status_code == 200
    assert "place" in types.json()["types"]

    detail = public_client.get(
        f"/public/v1/projects/general/locations/{location_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["formatted_address"] == "123 Main St"

    mentions = public_client.get(
        f"/public/v1/projects/general/locations/{location_id}/mentions",
        headers=headers,
    )
    assert mentions.status_code == 200
    mbody = mentions.json()
    assert mbody["label"] == "City Hall"
    assert mbody["pagination"]["total"] == 1
    assert mbody["items"][0]["nature"] == "primary"

    quoted = public_client.get(
        f"/public/v1/projects/general/locations/{location_id}/mentions",
        headers=headers,
        params={"quote": "true"},
    )
    assert quoted.status_code == 200
    assert quoted.json()["pagination"]["total"] == 1
    assert quoted.json()["items"][0]["evidence"]["mention_text"] == "debate downtown"
    assert quoted.json()["items"][0]["evidence"]["quote"] is True
    assert "quote_text" not in quoted.json()["items"][0]["evidence"]

    articles = public_client.get(
        f"/public/v1/projects/general/locations/{location_id}/articles",
        headers=headers,
    )
    assert articles.status_code == 200
    assert articles.json()["pagination"]["total"] == 1
    assert articles.json()["items"][0]["headline"] == "City council votes on budget"

    connections = public_client.get(
        f"/public/v1/projects/general/locations/{location_id}/connections",
        headers=headers,
    )
    assert connections.status_code == 200
    assert len(connections.json()["connections"]) == 1
    assert connections.json()["connections"][0]["nature"] == "works_at"


def test_public_location_not_found(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/locations/00000000-0000-4000-8000-000000009999",
        headers=headers,
    )
    assert r.status_code == 404


def test_public_mentions_search_facets_and_detail(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    searched = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
    )
    assert searched.status_code == 200
    body = searched.json()
    assert body["pagination"]["total"] == 3
    entity_types = {item["entity_type"] for item in body["items"]}
    assert entity_types == {"location", "person", "organization"}
    assert all(
        item["article"]["headline"] == "City council votes on budget"
        for item in body["items"]
    )

    by_person = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params={"entity_type": "person", "nature": "subject"},
    )
    assert by_person.status_code == 200
    pbody = by_person.json()
    assert pbody["pagination"]["total"] == 1
    assert pbody["items"][0]["label"] == "Jane Doe"
    person_mention_id = pbody["items"][0]["mention_id"]

    by_author = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params={"author": "Jane Doe"},
    )
    assert by_author.status_code == 200
    assert by_author.json()["pagination"]["total"] == 3

    facets = public_client.get("/public/v1/projects/general/mentions/facets", headers=headers)
    assert facets.status_code == 200
    fbody = facets.json()
    assert set(fbody["entity_types"]) == {"location", "person", "organization"}
    assert "primary" in fbody["natures"]
    assert "place" in fbody["location_types"]

    detail = public_client.get(
        f"/public/v1/projects/general/mentions/person/{person_mention_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["label"] == "Jane Doe"
    assert detail.json()["occurrences"]
    assert detail.json()["canonical"]["label"] == "Jane Doe"


def test_public_mentions_search_quote_filter(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params={"quote": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["entity_type"] == "location"
    assert body["items"][0]["evidence"]["mention_text"] == "debate downtown"
    assert body["items"][0]["evidence"]["quote"] is True
    assert "quote_text" not in body["items"][0]["evidence"]


def test_public_mention_not_found(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/mentions/person/999999",
        headers=headers,
    )
    assert r.status_code == 404

    bad_type = public_client.get(
        "/public/v1/projects/general/mentions/invalid/1",
        headers=headers,
    )
    assert bad_type.status_code == 404


def test_public_mentions_search_meta_clauses(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    matched = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params=[("meta", "topic:local_government_politics")],
    )
    assert matched.status_code == 200
    assert matched.json()["pagination"]["total"] == 3

    excluded = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params=[("meta", "topic:sports")],
    )
    assert excluded.status_code == 200
    assert excluded.json()["pagination"]["total"] == 0


def test_public_mentions_search_meta_clauses_invalid(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}
    r = public_client.get(
        "/public/v1/projects/general/mentions/search",
        headers=headers,
        params=[("meta", "topic:")],
    )
    assert r.status_code == 400


@patch("core_api.routers.public.articles.semantic_search.embed_semantic_search_query")
def test_public_article_semantic_search_meta_clauses(
    mock_embed: MagicMock,
    public_client: TestClient,
) -> None:
    mock_embed.return_value = SemanticQueryEmbedding(
        vector=[1.0, 0.0],
        model_config_id="emb-test",
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=2,
    )
    raw_key = _create_project_api_key(public_client)
    headers = {"Authorization": f"Bearer {raw_key}"}

    matched = public_client.post(
        "/public/v1/projects/general/articles/semantic-search",
        headers=headers,
        json={"query": "city budget debate", "meta": ["topic:local_government_politics"]},
    )
    assert matched.status_code == 200
    assert matched.json()["pagination"]["total"] == 1

    excluded = public_client.post(
        "/public/v1/projects/general/articles/semantic-search",
        headers=headers,
        json={"query": "city budget debate", "meta": ["topic:sports"]},
    )
    assert excluded.status_code == 200
    assert excluded.json()["pagination"]["total"] == 0
