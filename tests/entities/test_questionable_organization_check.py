"""Tests for questionable organization cleanup check item construction."""

from __future__ import annotations

import json

import pytest
from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.quality.check_runs import CleanupRunScope
from backfield_entities.quality.dismissals import dismiss_canonical_issue
from backfield_entities.quality.finders.questionable_organizations import (
    build_questionable_organization_check_items,
    prefilter_questionable_organization_canonicals,
)
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def questionable_org_engine(tmp_path) -> Engine:
    database_path = tmp_path / "questionable-org-check.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        sb = Stylebook(
            organization_id=int(org.id),
            slug="default",
            name="Default",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="donald-trump-person",
                label="Donald Trump",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="donald-trump-org",
                label="Donald Trump",
                organization_type="government",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="chicago-dept-law",
                label="Chicago Department of Law",
                organization_type="government",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="american-civil-society",
                label="American civil society",
                organization_type="other",
            )
        )
        session.commit()
    return engine


def test_prefilter_questionable_organization_canonicals_filters_active_rows(
    questionable_org_engine: Engine,
) -> None:
    with Session(questionable_org_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        prefiltered = prefilter_questionable_organization_canonicals(
            session,
            stylebook_id=int(sb.id),
        )
    labels = {str(row.label) for row, _score, _signals in prefiltered}
    assert "Donald Trump" in labels
    assert "American civil society" in labels
    assert "Chicago Department of Law" not in labels


def test_build_questionable_organization_check_items_uses_llm_for_cross_catalog_person(
    questionable_org_engine: Engine,
) -> None:
    with Session(questionable_org_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        org = session.exec(select(BackfieldOrganization)).one()
        trump = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug == "donald-trump-org"
            )
        ).one()
        trump_id = str(trump.id)

        def mock_call_llm(prompt: str, **_kwargs: object) -> str:
            assert trump_id in prompt
            assert "catalog_collision=person_canonical_same_label" in prompt
            return json.dumps(
                {
                    "results": [
                        {
                            "canonical_id": trump_id,
                            "decision": "flag",
                            "category": "person_like",
                            "confidence": "high",
                            "explanation": "This label names a person, not an institution.",
                            "suggested_entity_type": "person",
                        }
                    ]
                }
            )

        scope = CleanupRunScope(
            stylebook_id=int(sb.id),
            organization_id=int(org.id),
            check_id="questionable-organization-canonicals",
            full_threshold=0.84,
            head_threshold=0.75,
            project_ids=(),
            project_slug=None,
        )
        items = build_questionable_organization_check_items(
            session,
            scope=scope,
            call_llm=mock_call_llm,
        )
        trump_items = [item for item in items if item.item_key == trump_id]
        assert len(trump_items) == 1
        assert trump_items[0].label == "Donald Trump"
        assert trump_items[0].payload["llm_decision"] == "flag"
        assert trump_items[0].payload["category"] == "person_like"
        assert "cross_catalog_person" in trump_items[0].payload["prefilter_signals"]


def test_build_questionable_organization_check_items_uses_mock_llm_for_non_auto_rows(
    questionable_org_engine: Engine,
) -> None:
    with Session(questionable_org_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        org = session.exec(select(BackfieldOrganization)).one()
        descriptor = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug == "american-civil-society"
            )
        ).one()
        descriptor_id = str(descriptor.id)
        llm_called = {"value": False}

        def mock_call_llm(prompt: str, **_kwargs: object) -> str:
            llm_called["value"] = True
            assert descriptor_id in prompt
            return json.dumps(
                {
                    "results": [
                        {
                            "canonical_id": descriptor_id,
                            "decision": "flag",
                            "category": "generic_group",
                            "confidence": "high",
                            "explanation": "Broad descriptor, not a proper-noun institution.",
                            "suggested_entity_type": "none",
                        }
                    ]
                }
            )

        scope = CleanupRunScope(
            stylebook_id=int(sb.id),
            organization_id=int(org.id),
            check_id="questionable-organization-canonicals",
            full_threshold=0.84,
            head_threshold=0.75,
            project_ids=(),
            project_slug=None,
        )
        items = build_questionable_organization_check_items(
            session,
            scope=scope,
            call_llm=mock_call_llm,
        )
        assert llm_called["value"] is True
        descriptor_items = [item for item in items if item.item_key == descriptor_id]
        assert len(descriptor_items) == 1
        assert descriptor_items[0].payload["category"] == "generic_group"


def test_build_questionable_organization_check_items_hides_dismissed_rows(
    questionable_org_engine: Engine,
) -> None:
    with Session(questionable_org_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        org = session.exec(select(BackfieldOrganization)).one()
        trump = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug == "donald-trump-org"
            )
        ).one()
        trump_id = str(trump.id)
        dismiss_canonical_issue(
            session,
            stylebook_id=int(sb.id),
            check_id="questionable-organization-canonicals",
            canonical_id=trump_id,
        )
        session.commit()

        def mock_call_llm(prompt: str, **_kwargs: object) -> str:
            assert trump_id not in prompt
            return json.dumps({"results": []})

        scope = CleanupRunScope(
            stylebook_id=int(sb.id),
            organization_id=int(org.id),
            check_id="questionable-organization-canonicals",
            full_threshold=0.84,
            head_threshold=0.75,
            project_ids=(),
            project_slug=None,
        )
        items = build_questionable_organization_check_items(
            session,
            scope=scope,
            call_llm=mock_call_llm,
        )
        assert all(item.item_key != trump_id for item in items)
