"""Tests for custom record DBOutput persist."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateCustomRecord,
)
from backfield_entities.ingest.custom_record.persist import (
    persist_custom_records_after_db_output,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_article(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-custom-record")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="Demo",
        slug="demo-custom-record",
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


_SCHEMA = [
    {"name": "item", "label": "Item", "type": "string", "description": ""},
    {"name": "quantity", "label": "Quantity", "type": "string", "description": ""},
]


def _record(item: str, quantity: str, *, key: str = "") -> dict:
    return {
        "key": key or f"key-{item}",
        "fields": {"item": item, "quantity": quantity},
        "mentions": [{"text": f"{quantity} of {item}", "quote": False}],
        "confidence": 0.9,
    }


def _record_set(*records: dict) -> dict:
    return {
        "label": "Ingredients",
        "schema": _SCHEMA,
        "records": list(records),
        "dropped_ungrounded": 0,
    }


def _rows(session: Session, article_id: int, record_type: str) -> list[SubstrateCustomRecord]:
    return list(
        session.exec(
            select(SubstrateCustomRecord)
            .where(
                SubstrateCustomRecord.article_id == article_id,
                SubstrateCustomRecord.record_type == record_type,
            )
            .order_by(SubstrateCustomRecord.record_index)
        ).all()
    )


def test_persist_creates_rows_with_schema_snapshot() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {
                    "ingredients": _record_set(
                        _record("flour", "2 cups"),
                        _record("salt", "1 tsp"),
                    )
                }
            },
            policy="smart_merge",
            source_run_id="run-custom-1",
        )
        assert summary["status"] == "succeeded"
        assert summary["persisted"] is True
        assert summary["count"] == 2

        rows = _rows(session, article_id, "ingredients")
        assert [row.record_index for row in rows] == [0, 1]
        assert rows[0].fields_json == {"item": "flour", "quantity": "2 cups"}
        assert rows[0].mentions_json == [{"text": "2 cups of flour", "quote": False}]
        assert rows[0].field_schema_json == _SCHEMA
        assert rows[0].confidence == 0.9
        assert rows[0].source_run_id == "run-custom-1"


def test_rerun_replaces_rows_for_record_type() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {
                    "ingredients": _record_set(
                        _record("flour", "2 cups"),
                        _record("salt", "1 tsp"),
                    )
                }
            },
            policy="smart_merge",
        )
        session.commit()

        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"ingredients": _record_set(_record("butter", "1 stick"))}
            },
            policy="smart_merge",
        )
        session.commit()

        assert summary["record_types"][0]["action"] == "replaced"
        rows = _rows(session, article_id, "ingredients")
        assert len(rows) == 1
        assert rows[0].fields_json["item"] == "butter"


def test_sibling_record_types_are_untouched() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"ingredients": _record_set(_record("flour", "2 cups"))}
            },
            policy="smart_merge",
        )
        session.commit()

        persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"recipe_steps": _record_set(_record("mix", "step one"))}
            },
            policy="smart_merge",
        )
        session.commit()

        assert len(_rows(session, article_id, "ingredients")) == 1
        assert len(_rows(session, article_id, "recipe_steps")) == 1


def test_add_only_skips_existing_record_type() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"ingredients": _record_set(_record("flour", "2 cups"))}
            },
            policy="smart_merge",
        )
        session.commit()

        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"ingredients": _record_set(_record("butter", "1 stick"))}
            },
            policy="add_only",
        )
        assert summary["status"] == "skipped"
        rows = _rows(session, article_id, "ingredients")
        assert rows[0].fields_json["item"] == "flour"


def test_empty_records_list_clears_prior_rows_on_replace() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "custom_records": {"ingredients": _record_set(_record("flour", "2 cups"))}
            },
            policy="smart_merge",
        )
        session.commit()

        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={"custom_records": {"ingredients": _record_set()}},
            policy="replace",
        )
        session.commit()

        assert summary["status"] == "succeeded"
        assert _rows(session, article_id, "ingredients") == []


def test_malformed_records_are_skipped_with_warnings() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        record_set = _record_set(_record("flour", "2 cups"))
        record_set["records"].append({"fields": {"item": "salt"}, "mentions": []})
        record_set["records"].append("not an object")

        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={"custom_records": {"ingredients": record_set}},
            policy="smart_merge",
        )
        assert summary["status"] == "succeeded"
        assert summary["count"] == 1
        warnings = summary["record_types"][0]["warnings"]
        assert len(warnings) == 2


def test_missing_block_is_not_present() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={"text": "Body"},
            policy="smart_merge",
        )
        assert summary["status"] == "not_present"
        assert summary["persisted"] is False


def test_invalid_record_set_shape_fails() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_custom_records_after_db_output(
            session,
            article_id=article_id,
            consolidated={"custom_records": {"ingredients": {"records": []}}},
            policy="smart_merge",
        )
        assert summary["status"] == "failed"
        assert "schema" in summary["record_types"][0]["error"]
