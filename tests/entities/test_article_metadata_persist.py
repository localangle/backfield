"""Tests for article metadata DBOutput persist."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from backfield_entities.ingest.article_metadata.persist import (
    persist_article_metadata_after_db_output,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_article(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-article-meta")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="Demo",
        slug="demo-article-meta",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    article = SubstrateArticle(
        project_id=int(proj.id),  # type: ignore[arg-type]
        headline="Headline",
        text="Body",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return int(article.id)  # type: ignore[arg-type]


def _sample_block(**overrides: object) -> dict:
    base = {
        "meta_type": "topic",
        "category": "Local news",
        "rationale": "The story covers a city council vote.",
        "confidence": 0.82,
        "prompt_preset": "topic",
    }
    base.update(overrides)
    return base


def test_persist_creates_row() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
            source_run_id="run-meta-1",
        )
        assert summary["status"] == "succeeded"
        assert summary["persisted"] is True
        row = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "topic",
            )
        ).one()
        assert row.category == "Local news"
        assert row.source_run_id == "run-meta-1"


def test_add_only_skips_existing() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
        )
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": _sample_block(
                    category="Politics",
                    rationale="Different rationale",
                    confidence=0.55,
                )
            },
            policy="add_only",
        )
        assert summary["status"] == "skipped"
        row = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "topic",
            )
        ).one()
        assert row.category == "Local news"


def test_smart_merge_skips_unchanged() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
        )
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
        )
        assert summary["status"] == "skipped"
        assert summary["reason"] == "unchanged"


def test_replace_updates_existing_row() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
        )
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": _sample_block(
                    category="Politics",
                    rationale="Updated rationale",
                    confidence=0.91,
                )
            },
            policy="replace",
            source_run_id="run-meta-2",
        )
        assert summary["status"] == "succeeded"
        assert summary["action"] == "replaced"
        row = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "topic",
            )
        ).one()
        assert row.category == "Politics"
        assert row.rationale == "Updated rationale"
        assert row.confidence == 0.91
        assert row.source_run_id == "run-meta-2"


def test_missing_block_is_not_present_and_does_not_delete_existing() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_metadata": _sample_block()},
            policy="smart_merge",
        )
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={"text": "Body only"},
            policy="replace",
        )
        assert summary["status"] == "not_present"
        row = session.exec(
            select(SubstrateArticleMeta).where(SubstrateArticleMeta.article_id == article_id)
        ).one()
        assert row.category == "Local news"


def test_persist_subject_creates_multiple_rows() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": {
                    "meta_type": "subject",
                    "prompt_preset": "subject",
                    "category": "local_government_politics",
                    "rationale": "Council vote is central.",
                    "confidence": 0.92,
                    "subjects": [
                        {
                            "category": "local_government_politics",
                            "rationale": "Council vote is central.",
                            "confidence": 0.92,
                        },
                        {
                            "category": "housing_affordability_homelessness",
                            "rationale": "Affordable housing is a major theme.",
                            "confidence": 0.86,
                        },
                    ],
                }
            },
            policy="smart_merge",
        )
        assert summary["status"] == "succeeded"
        assert summary["item_count"] == 2
        rows = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "subject",
            )
        ).all()
        assert {row.category for row in rows} == {
            "local_government_politics",
            "housing_affordability_homelessness",
        }


def test_persist_subject_replace_drops_removed_categories() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": {
                    "meta_type": "subject",
                    "prompt_preset": "subject",
                    "category": "pro_sports",
                    "rationale": "Sports focus.",
                    "confidence": 0.95,
                    "subjects": [
                        {
                            "category": "pro_sports",
                            "rationale": "Sports focus.",
                            "confidence": 0.95,
                        }
                    ],
                }
            },
            policy="smart_merge",
        )
        persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": {
                    "meta_type": "subject",
                    "prompt_preset": "subject",
                    "category": "business_economy",
                    "rationale": "Business focus.",
                    "confidence": 0.91,
                    "subjects": [
                        {
                            "category": "business_economy",
                            "rationale": "Business focus.",
                            "confidence": 0.91,
                        }
                    ],
                }
            },
            policy="replace",
        )
        rows = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "subject",
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].category == "business_economy"


def test_persist_information_needs_creates_multiple_rows() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_article_metadata_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_metadata": {
                    "meta_type": "information_needs",
                    "prompt_preset": "information_needs",
                    "category": "education",
                    "rationale": "School access is central.",
                    "confidence": 0.94,
                    "needs": [
                        {
                            "category": "education",
                            "rationale": "School access is central.",
                            "confidence": 0.94,
                        },
                        {
                            "category": "political_information",
                            "rationale": "Board vote with policy implications.",
                            "confidence": 0.82,
                        },
                    ],
                }
            },
            policy="smart_merge",
        )
        assert summary["status"] == "succeeded"
        assert summary["item_count"] == 2
        rows = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == article_id,
                SubstrateArticleMeta.meta_type == "information_needs",
            )
        ).all()
        assert {row.category for row in rows} == {"education", "political_information"}
