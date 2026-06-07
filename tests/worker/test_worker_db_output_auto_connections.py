"""Worker Backfield Output automatic connection inference tests."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from backfield_db import (
    AgateRun,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookConnection,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.connections.db_output import run_auto_connections_for_db_output
from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings
from sqlmodel import Session, SQLModel, create_engine, select
from worker.nodes.db_output import run_db_output

from tests.worker.test_person_substrate_persistence import _sample_person_entry
from tests.worker.test_substrate_persistence import _bootstrap_project, _empty_places


@dataclass(frozen=True)
class LinkedPersonOrgFixture:
    project_id: int
    article_id: int
    person_canonical_id: str
    organization_canonical_id: str
    article_text: str


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _eligible_settings(**overrides: object) -> DbOutputCanonicalSettings:
    base = {
        "stylebook_matching_enabled": True,
        "canonicalization_mode": "ai_assisted",
        "auto_apply_canonicalization": True,
        "auto_connections_enabled": True,
        "adjudication_model": "gpt-5-nano",
    }
    base.update(overrides)
    return DbOutputCanonicalSettings.model_validate(base)


def _seed_linked_person_org(session: Session) -> LinkedPersonOrgFixture:
    project_id = _bootstrap_project(session, org_slug="org-conn", project_slug="proj-conn")
    proj = session.get(BackfieldProject, project_id)
    assert proj is not None
    ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
    assert ws is not None
    sb_id = int(ws.stylebook_id)

    person_canon = StylebookPersonCanonical(
        stylebook_id=sb_id,
        label="Jane Smith",
        slug="jane-smith",
        affiliation="Chicago City Hall",
        status="active",
    )
    org_canon = StylebookOrganizationCanonical(
        stylebook_id=sb_id,
        label="Chicago City Hall",
        slug="chicago-city-hall",
        organization_type="government",
        status="active",
    )
    session.add(person_canon)
    session.add(org_canon)
    session.commit()
    session.refresh(person_canon)
    session.refresh(org_canon)
    person_cid = str(person_canon.id)
    org_cid = str(org_canon.id)

    article_text = "Mayor Jane Smith works for Chicago City Hall, officials said."
    article = SubstrateArticle(
        project_id=project_id,
        url="https://example.com/conn",
        headline="Connection test article",
        text=article_text,
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    article_id = int(article.id)  # type: ignore[arg-type]

    person = SubstratePerson(
        project_id=project_id,
        name="Jane Smith",
        normalized_name="jane smith",
        affiliation="Chicago City Hall",
        identity_fingerprint="fp-conn-person",
        canonical_link_status=CANONICAL_LINK_LINKED,
        stylebook_person_canonical_id=person_cid,
    )
    organization = SubstrateOrganization(
        project_id=project_id,
        name="Chicago City Hall",
        normalized_name="chicago city hall",
        organization_type="government",
        identity_fingerprint="fp-conn-org",
        canonical_link_status=CANONICAL_LINK_LINKED,
        stylebook_organization_canonical_id=org_cid,
    )
    session.add(person)
    session.add(organization)
    session.commit()
    session.refresh(person)
    session.refresh(organization)

    person_mention = SubstratePersonMention(
        article_id=article_id,
        person_id=int(person.id),  # type: ignore[arg-type]
    )
    org_mention = SubstrateOrganizationMention(
        article_id=article_id,
        organization_id=int(organization.id),  # type: ignore[arg-type]
    )
    session.add(person_mention)
    session.add(org_mention)
    session.commit()
    session.refresh(person_mention)
    session.refresh(org_mention)

    session.add(
        SubstratePersonMentionOccurrence(
            person_mention_id=int(person_mention.id),  # type: ignore[arg-type]
            mention_text=article_text,
            occurrence_order=1,
        )
    )
    session.add(
        SubstrateOrganizationMentionOccurrence(
            organization_mention_id=int(org_mention.id),  # type: ignore[arg-type]
            mention_text=article_text,
            occurrence_order=1,
        )
    )
    session.commit()

    return LinkedPersonOrgFixture(
        project_id=project_id,
        article_id=article_id,
        person_canonical_id=person_cid,
        organization_canonical_id=org_cid,
        article_text=article_text,
    )


def _llm_edges_response(
    *,
    from_id: str,
    to_id: str,
    nature: str = "works_for",
    confidence: float = 0.95,
    quote: str,
) -> str:
    return json.dumps(
        {
            "edges": [
                {
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "nature": nature,
                    "confidence": confidence,
                    "quote": quote,
                    "reason": "Explicit relationship in text.",
                }
            ]
        }
    )


def test_auto_connections_ineligible_when_stylebook_matching_off() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(stylebook_matching_enabled=False),
            call_llm=MagicMock(),
        )
    assert summary["enabled"] is True
    assert summary["eligible"] is False
    assert summary["reason"] == "stylebook_matching_off"
    assert summary["created"] == 0


def test_auto_connections_ineligible_when_rules_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(canonicalization_mode="rules"),
            call_llm=MagicMock(),
        )
    assert summary["eligible"] is False
    assert summary["reason"] == "canonicalization_not_ai_assisted"


def test_auto_connections_ineligible_when_auto_apply_off() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(auto_apply_canonicalization=False),
            call_llm=MagicMock(),
        )
    assert summary["eligible"] is False
    assert summary["reason"] == "auto_apply_off"


def test_auto_connections_creates_high_confidence_edge() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        quote = "Mayor Jane Smith works for Chicago City Hall"
        mock_llm = MagicMock(
            return_value=_llm_edges_response(
                from_id=fixture.person_canonical_id,
                to_id=fixture.organization_canonical_id,
                quote=quote,
            )
        )
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(),
            run_id="run-conn-create",
            call_llm=mock_llm,
        )
        session.commit()

    assert summary["status"] == "succeeded"
    assert summary["created"] == 1
    assert summary["edges"][0]["nature"] == "works_for"
    mock_llm.assert_called_once()

    with Session(engine) as session:
        rows = session.exec(select(StylebookConnection)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.from_entity_type == "person"
        assert row.from_entity_id == fixture.person_canonical_id
        assert row.to_entity_type == "organization"
        assert row.to_entity_id == fixture.organization_canonical_id
        assert row.nature == "works_for"
        assert row.evidence_json is not None
        assert row.evidence_json["quote"] == quote
        assert row.evidence_json["confidence"] == 0.95


def test_auto_connections_skips_low_confidence_edge() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        quote = "Mayor Jane Smith works for Chicago City Hall"
        mock_llm = MagicMock(
            return_value=_llm_edges_response(
                from_id=fixture.person_canonical_id,
                to_id=fixture.organization_canonical_id,
                confidence=0.7,
                quote=quote,
            )
        )
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(),
            call_llm=mock_llm,
        )
        session.commit()

    assert summary["created"] == 0
    assert summary["skipped"] >= 1
    with Session(engine) as session:
        assert session.exec(select(StylebookConnection)).all() == []


def test_auto_connections_skips_duplicate_existing_edge() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        session.add(
            StylebookConnection(
                project_id=fixture.project_id,
                from_entity_type="person",
                from_entity_id=fixture.person_canonical_id,
                to_entity_type="organization",
                to_entity_id=fixture.organization_canonical_id,
                nature="works_for",
            )
        )
        session.commit()

        quote = "Mayor Jane Smith works for Chicago City Hall"
        mock_llm = MagicMock(
            return_value=_llm_edges_response(
                from_id=fixture.person_canonical_id,
                to_id=fixture.organization_canonical_id,
                quote=quote,
            )
        )
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(),
            call_llm=mock_llm,
        )
        session.commit()

    assert summary["created"] == 0
    assert summary["skipped_existing"] == 1
    with Session(engine) as session:
        assert len(session.exec(select(StylebookConnection)).all()) == 1


def test_auto_connections_skips_invalid_llm_json() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_linked_person_org(session)
        summary = run_auto_connections_for_db_output(
            session,
            project_id=fixture.project_id,
            article_id=fixture.article_id,
            article_text=fixture.article_text,
            settings=_eligible_settings(),
            call_llm=MagicMock(return_value="not json"),
        )
        session.commit()

    assert summary["created"] == 0
    assert summary["families"][0]["skip_reasons"].get("invalid_llm_json") == 1


@patch("backfield_entities.connections.db_output.collect_auto_connection_article_context")
def test_run_db_output_succeeds_when_inference_raises(mock_collect: MagicMock) -> None:
    mock_collect.side_effect = RuntimeError("inference blew up")

    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-conn-fail",
        "BACKFIELD_RUN_ID": "run-conn-fail",
    }
    consolidated = {
        "text": "Mayor Jane Smith announced a new policy today.",
        "url": "https://example.com/conn-fail",
        "people": [_sample_person_entry()],
        "places": _empty_places(),
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-conn-fail", project_slug="proj-conn-fail"
        )
        session.add(AgateRun(id="run-conn-fail", graph_id="graph-conn-fail", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {
                    "stylebook_matching_enabled": True,
                    "canonicalization_mode": "ai_assisted",
                    "auto_apply_canonicalization": True,
                    "auto_connections_enabled": True,
                },
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["connections"]["status"] == "failed"
    assert "inference blew up" in out["connections"]["error"]


@patch("worker.nodes.db_output.run_auto_connections_for_db_output")
def test_run_db_output_reports_ineligible_connections(mock_run: MagicMock) -> None:
    mock_run.return_value = {
        "enabled": True,
        "eligible": False,
        "status": "ineligible",
        "reason": "stylebook_matching_off",
        "created": 0,
        "skipped_existing": 0,
        "families": [],
    }

    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-conn-inel",
        "BACKFIELD_RUN_ID": "run-conn-inel",
    }
    consolidated = {
        "text": "Mayor Jane Smith announced a new policy today.",
        "url": "https://example.com/conn-inel",
        "people": [_sample_person_entry()],
        "places": _empty_places(),
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-conn-inel", project_slug="proj-conn-inel"
        )
        session.add(AgateRun(id="run-conn-inel", graph_id="graph-conn-inel", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {"stylebook_matching_enabled": False, "auto_connections_enabled": True},
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["connections"]["eligible"] is False
    mock_run.assert_called_once()
