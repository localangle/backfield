"""Tests for repairing legacy S3 article external_source values."""

from __future__ import annotations

import json
from uuid import uuid4

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    AgateS3IngestionLedger,
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.ingest.article_external_identity import (
    S3_INGESTION_EXTERNAL_SOURCE,
    publication_and_url_from_processed_item,
    repair_s3_article_external_sources,
    resolve_article_outlet_external_source,
)
from sqlmodel import Session, SQLModel, create_engine

from tests.project_helpers import project_ownership_fields


def _project(session: Session, *, slug: str = "news") -> int:
    org = BackfieldOrganization(name="Org", slug=f"org-{slug}")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    ensure_default_stylebook_for_organization(session, oid)
    project = BackfieldProject(
        **project_ownership_fields(session, oid),
        name="News",
        slug=slug,
        organization_id=oid,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return int(project.id)  # type: ignore[arg-type]


def test_resolve_article_outlet_external_source_order() -> None:
    assert (
        resolve_article_outlet_external_source(
            publication=" Chicago Sun-Times ",
            url="https://example.com/a",
        )
        == "Chicago Sun-Times"
    )
    assert (
        resolve_article_outlet_external_source(
            publication="  ",
            url="https://www.suntimes.com/story",
        )
        == "suntimes.com"
    )
    assert (
        resolve_article_outlet_external_source(publication=None, url=None)
        == "backfield_text_fingerprint"
    )


def test_publication_prefers_reviewed_output_json() -> None:
    item = AgateProcessedItem(
        run_id="run-1",
        result_json=json.dumps({"publication": "From result", "url": "https://a.example/1"}),
        reviewed_output_json=json.dumps(
            {"publication": "From review", "url": "https://b.example/2"}
        ),
    )
    assert publication_and_url_from_processed_item(item) == (
        "From review",
        "https://b.example/2",
    )


def test_repair_s3_article_sources_dry_run_and_apply() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _project(session)
        graph = AgateGraph(name="G", spec_json="{}", project_id=project_id)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        run = AgateRun(graph_id=str(graph.id), status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        ledger = AgateS3IngestionLedger(
            project_id=project_id,
            source_id="src",
            logical_item_id="bucket/a.json",
            bucket="bucket",
            key="a.json",
            content_fingerprint="fp",
            status="succeeded",
            claim_token=str(uuid4()),
            attempt_count=1,
            flow_run_id=str(run.id),
        )
        session.add(ledger)
        session.commit()
        session.refresh(ledger)
        item = AgateProcessedItem(
            run_id=str(run.id),
            result_json=json.dumps({"publication": "Chicago Sun-Times"}),
            ingestion_ledger_id=str(ledger.id),
            status="succeeded",
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        article = SubstrateArticle(
            project_id=project_id,
            external_source=S3_INGESTION_EXTERNAL_SOURCE,
            external_id=str(ledger.id),
            headline="H",
            text="t",
            source_item_id=int(item.id),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        dry = repair_s3_article_external_sources(session, apply=False)
        session.refresh(article)
        assert dry.scanned == 1
        assert dry.updated == 1
        assert article.external_source == S3_INGESTION_EXTERNAL_SOURCE

        applied = repair_s3_article_external_sources(session, apply=True)
        session.refresh(article)
        assert applied.updated == 1
        assert article.external_source == "Chicago Sun-Times"
        assert article.external_id == str(ledger.id)
        assert int(article.id) == article_id


def test_repair_s3_article_sources_skips_unique_collisions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _project(session, slug="collide")
        ledger_id = str(uuid4())
        session.add(
            SubstrateArticle(
                project_id=project_id,
                external_source="backfield_text_fingerprint",
                external_id=ledger_id,
                headline="Existing fingerprint row",
                text="a",
            )
        )
        legacy = SubstrateArticle(
            project_id=project_id,
            external_source=S3_INGESTION_EXTERNAL_SOURCE,
            external_id=ledger_id,
            headline="Legacy S3 row",
            text="b",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)

        report = repair_s3_article_external_sources(session, apply=True)
        session.refresh(legacy)
        assert report.collision_skipped == 1
        assert report.updated == 0
        assert legacy.external_source == S3_INGESTION_EXTERNAL_SOURCE
