"""Unit tests for ``processed_item_article_context``."""

from __future__ import annotations

from api.processed_item_article_context import build_processed_item_article_context
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
)
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select


def _org_and_project(session: Session) -> tuple[int, int]:
    session.add(BackfieldOrganization(name="Org", slug="org-art"))
    session.commit()
    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == "org-art")
    ).one()
    oid = int(org.id)
    slug = f"proj-art-{oid}"
    session.add(
        BackfieldProject(
            organization_id=oid,
            name="Proj",
            slug=slug,
        )
    )
    session.commit()
    proj = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).one()
    return oid, int(proj.id)


def test_article_context_substrate_success() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _oid, pid = _org_and_project(session)
        art = SubstrateArticle(
            project_id=pid,
            headline="H1",
            text="Full body here",
            url=f"https://example.com/a-{pid}",
        )
        session.add(art)
        session.commit()
        session.refresh(art)
        aid = int(art.id)

        ctx = build_processed_item_article_context(
            session,
            project_id=pid,
            input_obj={"input_article_id": aid},
        )
        assert ctx["resolution"] == "substrate"
        assert ctx["article_id"] == aid
        assert ctx["body"] == "Full body here"
        assert ctx["headline"] == "H1"
        assert ctx["reason"] is None


def test_article_context_inline_when_no_id() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _oid, pid = _org_and_project(session)
        ctx = build_processed_item_article_context(
            session,
            project_id=pid,
            input_obj={"article_text": "short", "body": "longer inline body"},
        )
        assert ctx["resolution"] == "inline_fallback"
        assert ctx["reason"] == "no_input_article_id"
        assert ctx["body"] == "longer inline body"


def test_article_context_not_found_uses_fallback() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _oid, pid = _org_and_project(session)
        ctx = build_processed_item_article_context(
            session,
            project_id=pid,
            input_obj={"input_article_id": 99999, "text": "fallback copy"},
        )
        assert ctx["resolution"] == "inline_fallback"
        assert ctx["reason"] == "article_not_found"
        assert ctx["body"] == "fallback copy"


def test_article_context_deleted_uses_fallback() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _oid, pid = _org_and_project(session)
        art = SubstrateArticle(
            project_id=pid,
            headline="Del",
            text="gone",
            url=f"https://example.com/del-{pid}",
            deleted=True,
        )
        session.add(art)
        session.commit()
        session.refresh(art)
        aid = int(art.id)
        ctx = build_processed_item_article_context(
            session,
            project_id=pid,
            input_obj={"input_article_id": aid, "article_text": "still here"},
        )
        assert ctx["resolution"] == "inline_fallback"
        assert ctx["reason"] == "article_deleted"
        assert ctx["body"] == "still here"


def test_article_context_project_mismatch() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        oid, pid_a = _org_and_project(session)
        slug_b = f"other-art-{pid_a}"
        session.add(
            BackfieldProject(
                organization_id=oid,
                name="Other",
                slug=slug_b,
            )
        )
        session.commit()
        proj_b = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug_b)).one()
        pid_b = int(proj_b.id)

        art = SubstrateArticle(
            project_id=pid_b,
            headline="Other proj",
            text="secret",
            url=f"https://example.com/other-{pid_b}",
        )
        session.add(art)
        session.commit()
        session.refresh(art)
        aid = int(art.id)

        ctx = build_processed_item_article_context(
            session,
            project_id=pid_a,
            input_obj={"input_article_id": aid, "text": "safe"},
        )
        assert ctx["resolution"] == "inline_fallback"
        assert ctx["reason"] == "article_project_mismatch"
        assert ctx["body"] == "safe"
