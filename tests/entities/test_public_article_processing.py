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
from sqlmodel import Session, SQLModel, create_engine


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
                meta_type="subject",
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
                    {"stylebook_output": {"success": True, "article_id": article_id}}
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
