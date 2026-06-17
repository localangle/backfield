"""Tests for public article processing provenance."""

from __future__ import annotations

import json

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateCustomRecord,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.article_processing import list_public_article_processing
from sqlmodel import Session, SQLModel, create_engine, select


def _seed_project(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Backfield", slug="default")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = ensure_default_stylebook_for_organization(session, int(org.id))
    ws = BackfieldWorkspace(
        organization_id=int(org.id),
        stylebook_id=int(sb.id),  # type: ignore[arg-type]
        name="Default Workspace",
        slug="default",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    project = BackfieldProject(
        name="General",
        slug="general",
        organization_id=int(org.id),
        workspace_id=int(ws.id),
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    article = SubstrateArticle(
        project_id=int(project.id),
        headline="Story",
        text="Body",
        source_run_id="run-latest",
        source_item_id=99,
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return int(project.id), int(article.id)  # type: ignore[arg-type]


def test_list_public_article_processing_collects_runs_and_items() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        session.add(
            SubstrateArticleMeta(
                article_id=article_id,
                meta_type="topic",
                category="news",
                rationale="r",
                confidence=0.9,
                source_run_id="run-meta",
            )
        )
        session.add(
            SubstrateCustomRecord(
                article_id=article_id,
                record_type="contracts",
                record_index=0,
                fields_json={},
                mentions_json=[],
                field_schema_json=[],
                source_run_id="run-custom",
            )
        )
        graph = AgateGraph(
            id="graph-1",
            name="Flow",
            spec_json="{}",
            project_id=project_id,
        )
        session.add(graph)
        session.add(AgateRun(id="run-meta", graph_id="graph-1", status="succeeded"))
        session.add(
            AgateProcessedItem(
                id=42,
                run_id="run-meta",
                status="succeeded",
                result_json=json.dumps(
                    {
                        "stylebook_output": {
                            "success": True,
                            "article_id": article_id,
                            "reconciliation": {
                                "domains": [
                                    {"domain": "places", "policy": "merge"},
                                    {"domain": "people", "policy": "merge"},
                                ]
                            },
                            "article_metadata_persist": {
                                "status": "succeeded",
                                "persisted": True,
                            },
                        }
                    }
                ),
            )
        )
        session.commit()

        rows = list_public_article_processing(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        assert {(row.run_id, row.processed_item_id) for row in rows} == {
            ("run-latest", 99),
            ("run-meta", 42),
            ("run-custom", None),
        }
        by_run = {row.run_id: row for row in rows}
        assert by_run["run-meta"].domains == ["places", "people", "metadata"]
        assert by_run["run-custom"].domains == ["custom_records"]
        assert by_run["run-latest"].domains == []


def _stylebook_result_json(*, article_id: int, domains: list[str] | None = None) -> str:
    domain_rows = [{"domain": d, "policy": "merge"} for d in (domains or ["article"])]
    return json.dumps(
        {
            "stylebook_output": {
                "success": True,
                "article_id": article_id,
                "reconciliation": {"domains": domain_rows},
            }
        }
    )


def test_list_public_article_processing_uses_substrate_article_id_column() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        graph = AgateGraph(
            id="graph-1",
            name="Flow",
            spec_json="{}",
            project_id=project_id,
        )
        session.add(graph)
        session.add(AgateRun(id="run-indexed", graph_id="graph-1", status="succeeded"))
        session.add(
            AgateProcessedItem(
                id=55,
                run_id="run-indexed",
                status="succeeded",
                substrate_article_id=article_id,
                result_json=None,
            )
        )
        session.commit()

        rows = list_public_article_processing(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        assert ("run-indexed", 55) in {(row.run_id, row.processed_item_id) for row in rows}


def test_list_public_article_processing_uses_source_pointer_without_column() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        graph = AgateGraph(
            id="graph-1",
            name="Flow",
            spec_json="{}",
            project_id=project_id,
        )
        session.add(graph)
        session.add(AgateRun(id="run-latest", graph_id="graph-1", status="succeeded"))
        session.add(
            AgateProcessedItem(
                id=99,
                run_id="run-latest",
                status="succeeded",
                result_json=None,
            )
        )
        session.commit()

        rows = list_public_article_processing(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        assert ("run-latest", 99) in {(row.run_id, row.processed_item_id) for row in rows}


def test_list_public_article_processing_includes_prior_runs_after_reprocess() -> None:
    """Re-run overwrites article provenance but older processed items still appear."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        article = session.get(SubstrateArticle, article_id)
        assert article is not None
        article.source_run_id = "run-b"
        article.source_item_id = 200
        session.add(article)

        graph = AgateGraph(
            id="graph-1",
            name="Flow",
            spec_json="{}",
            project_id=project_id,
        )
        session.add(graph)
        session.add(AgateRun(id="run-a", graph_id="graph-1", status="succeeded"))
        session.add(AgateRun(id="run-b", graph_id="graph-1", status="succeeded"))
        session.add(
            AgateProcessedItem(
                id=100,
                run_id="run-a",
                status="succeeded",
                substrate_article_id=article_id,
                result_json=_stylebook_result_json(article_id=article_id, domains=["places"]),
            )
        )
        session.add(
            AgateProcessedItem(
                id=200,
                run_id="run-b",
                status="succeeded",
                substrate_article_id=article_id,
                result_json=_stylebook_result_json(article_id=article_id, domains=["metadata"]),
            )
        )
        session.commit()

        rows = list_public_article_processing(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        assert {(row.run_id, row.processed_item_id) for row in rows} == {
            ("run-b", 200),
            ("run-a", 100),
        }
        by_run = {row.run_id: row for row in rows}
        assert by_run["run-a"].domains == ["places"]
        assert by_run["run-b"].domains == ["metadata"]


def test_list_public_article_processing_dedupes_pointer_and_scan_paths() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        graph = AgateGraph(
            id="graph-1",
            name="Flow",
            spec_json="{}",
            project_id=project_id,
        )
        session.add(graph)
        session.add(AgateRun(id="run-meta", graph_id="graph-1", status="succeeded"))
        session.add(
            AgateProcessedItem(
                id=42,
                run_id="run-meta",
                status="succeeded",
                result_json=_stylebook_result_json(article_id=article_id, domains=["people"]),
            )
        )
        session.add(
            SubstrateArticleMeta(
                article_id=article_id,
                meta_type="topic",
                category="news",
                rationale="r",
                confidence=0.9,
                source_run_id="run-meta",
            )
        )
        session.commit()

        rows = list_public_article_processing(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        meta_rows = [
            row
            for row in rows
            if row.run_id == "run-meta" and row.processed_item_id == 42
        ]
        assert len(meta_rows) == 1


_MINIMAL_GRAPH_SPEC_JSON = json.dumps(
    {
        "name": "null-byte-regression",
        "nodes": [{"id": "out", "type": "Output", "params": {}}],
        "edges": [],
    }
)


def test_list_public_article_processing_handles_null_unicode_in_result_json() -> None:
    """Postgres jsonb text extraction rejects \\u0000; sanitized SQL must still match."""
    import os
    import uuid

    import pytest
    from backfield_db import BackfieldProject

    database_url = os.environ.get(
        "BACKFIELD_DATABASE_URL_DIRECT",
        "postgresql+psycopg://postgres:postgres@localhost:5433/backfield",
    )
    if not database_url.startswith("postgresql"):
        pytest.skip("postgres-only regression for sanitized article provenance SQL")

    engine = create_engine(database_url)
    with Session(engine) as session:
        bind = session.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            pytest.skip("postgres-only regression for sanitized article provenance SQL")

        project = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "general")
        ).first()
        if project is None or project.id is None:
            pytest.skip("general project seed data required for postgres regression test")

        project_id = int(project.id)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Null-byte regression article",
            text="Body",
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        if article.id is None:
            pytest.skip("failed to create regression article")
        article_id = int(article.id)
        run_id = f"run-null-byte-{uuid.uuid4().hex[:8]}"
        graph_id = f"graph-null-byte-{uuid.uuid4().hex[:8]}"
        item_id = int(uuid.uuid4().int % 2_000_000_000)

        session.add(
            AgateGraph(
                id=graph_id,
                name="Null-byte regression",
                spec_json=_MINIMAL_GRAPH_SPEC_JSON,
                project_id=project_id,
            )
        )
        session.commit()
        session.add(AgateRun(id=run_id, graph_id=graph_id, status="succeeded"))
        session.commit()
        session.add(
            AgateProcessedItem(
                id=item_id,
                run_id=run_id,
                status="succeeded",
                result_json=(
                    '{"stylebook_output":{"article_id":'
                    f"{article_id}"
                    '},"place_extract":{"mentions":[{"original_text":"Plus :\\u0000end"}]}}'
                ),
            )
        )
        session.commit()

        try:
            rows = list_public_article_processing(
                session,
                project_id=project_id,
                article_id=article_id,
            )
            assert (run_id, item_id) in {(row.run_id, row.processed_item_id) for row in rows}
        finally:
            session.rollback()
            session.delete(session.get(AgateProcessedItem, item_id))
            session.delete(session.get(AgateRun, run_id))
            session.delete(session.get(AgateGraph, graph_id))
            session.delete(session.get(SubstrateArticle, article_id))
            session.commit()
