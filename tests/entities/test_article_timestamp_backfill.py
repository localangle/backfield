"""Tests for article published/updated timestamp backfill."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.ingest.article_timestamps import (
    backfill_article_timestamps,
    parse_article_timestamp,
    published_and_updated_from_processed_item,
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


def test_parse_article_timestamp_rules() -> None:
    assert parse_article_timestamp("2026-08-19T16:37:29.350000-05:00") == datetime(
        2026, 8, 19, 21, 37, 29, 350000, tzinfo=UTC
    )
    assert parse_article_timestamp("2026-08-19T18:30:00") == datetime(
        2026, 8, 19, 18, 30, tzinfo=UTC
    )
    assert parse_article_timestamp("2026-08-19") is None
    assert parse_article_timestamp("not-a-timestamp") is None
    assert parse_article_timestamp(0) is None


def test_processed_item_prefers_reviewed_then_result_then_input() -> None:
    item = AgateProcessedItem(
        run_id="run-1",
        input_json=json.dumps({"updated": "2026-01-01T00:00:00Z"}),
        result_json=json.dumps(
            {
                "stylebook_output": {
                    "updated": "2026-02-01T00:00:00Z",
                    "reconciliation": {"domains": [{"updated": 0}]},
                }
            }
        ),
        reviewed_output_json=json.dumps(
            {"published": "2026-03-01T12:00:00-05:00", "updated": "2026-03-02T00:00:00Z"}
        ),
    )
    published, updated = published_and_updated_from_processed_item(item)
    assert published == datetime(2026, 3, 1, 17, 0, tzinfo=UTC)
    assert updated == datetime(2026, 3, 2, 0, 0, tzinfo=UTC)


def test_backfill_article_timestamps_dry_run_and_apply() -> None:
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

        item = AgateProcessedItem(
            run_id=str(run.id),
            status="succeeded",
            input_json=json.dumps(
                {
                    "pub_date": "2026-08-19",
                    "updated": "2026-08-19T16:37:29.350000-05:00",
                }
            ),
            result_json=json.dumps(
                {
                    "s3_input": {
                        "pub_date": "2026-08-19",
                        "updated": "2026-08-19T16:37:29.350000-05:00",
                    },
                    "stylebook_output": {
                        "updated": "2026-08-19T16:37:29.350000-05:00",
                        "reconciliation": {"domains": [{"updated": 0}]},
                    },
                }
            ),
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        article = SubstrateArticle(
            project_id=project_id,
            headline="Story",
            text="Body",
            pub_date=datetime(2026, 8, 19).date(),
            source_item_id=int(item.id),  # type: ignore[arg-type]
            source_run_id=str(run.id),
        )
        already = SubstrateArticle(
            project_id=project_id,
            headline="Already stamped",
            text="Body",
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            published=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        )
        no_source = SubstrateArticle(
            project_id=project_id,
            headline="No JSON",
            text="Body",
        )
        session.add(article)
        session.add(already)
        session.add(no_source)
        session.commit()
        session.refresh(article)
        session.refresh(item)
        item.substrate_article_id = int(article.id)  # type: ignore[arg-type]
        session.add(item)
        session.commit()
        article_id = int(article.id)  # type: ignore[arg-type]

        dry = backfill_article_timestamps(session, apply=False)
        assert dry.scanned == 2  # article + no_source; already has both set
        assert dry.updated_filled == 1
        assert dry.published_filled == 0
        assert dry.missing_source == 1
        assert dry.article_ids_updated == [article_id]
        session.refresh(article)
        assert article.updated is None

        applied = backfill_article_timestamps(session, apply=True)
        assert applied.updated_filled == 1
        session.refresh(article)
        stored_updated = article.updated
        assert stored_updated is not None
        if stored_updated.tzinfo is None:
            stored_updated = stored_updated.replace(tzinfo=UTC)
        assert stored_updated == datetime(2026, 8, 19, 21, 37, 29, 350000, tzinfo=UTC)
        assert article.published is None

        second = backfill_article_timestamps(session, apply=True)
        assert second.updated_filled == 0
        assert second.unchanged >= 1
