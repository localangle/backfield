"""Worker substrate persistence tests for consolidated ``organizations`` payloads."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import execute_graph
from agate_runtime.starter_flow import starter_organizations_flow_graph_spec
from backfield_db import (
    AgateRun,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstrateOrganizationSemanticDocument,
)
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_PENDING
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate import persist_from_consolidated
from worker.substrate.entities.registry import get_persist_handler, registered_consolidated_keys

from tests.worker.test_substrate_persistence import _bootstrap_project


def _sample_organization_entry(*, name: str = "Chicago City Hall") -> dict:
    return {
        "name": name,
        "type": "government",
        "role_in_story": "Announced a new policy",
        "nature": "actor",
        "nature_secondary_tags": ["source"],
        "mentions": [
            {
                "text": "Chicago City Hall announced a new policy today.",
                "quote": False,
            },
            {
                "text": '"This will benefit all residents," a spokesperson said.',
                "quote": True,
            },
        ],
    }


def test_registered_organizations_handler() -> None:
    assert "organizations" in registered_consolidated_keys()
    handler = get_persist_handler("organizations")
    assert handler is not None
    assert handler.consolidated_key == "organizations"


def test_persist_organizations_writes_substrate_mention_occurrence() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    body = (
        "Chicago City Hall announced a new policy today. "
        '"This will benefit all residents," a spokesperson said.'
    )

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-orgs", project_slug="proj-orgs")
        session.add(AgateRun(id="run-o1", graph_id="graph-o1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-o1",
            run_id="run-o1",
            consolidated={
                "text": body,
                "url": "https://example.com/orgs-1",
                "organizations": [_sample_organization_entry()],
            },
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

    with Session(engine) as session:
        orgs = session.exec(select(SubstrateOrganization)).all()
        assert len(orgs) == 1
        organization = orgs[0]
        assert organization.name == "Chicago City Hall"
        assert organization.organization_type == "government"
        assert organization.identity_fingerprint
        assert organization.canonical_link_status == CANONICAL_LINK_PENDING

        mentions = session.exec(select(SubstrateOrganizationMention)).all()
        assert len(mentions) == 1
        assert mentions[0].nature == "actor"
        assert mentions[0].nature_secondary_tags_json == ["source"]
        assert mentions[0].role_in_story == "Announced a new policy"

        occ = session.exec(
            select(SubstrateOrganizationMentionOccurrence).order_by(
                col(SubstrateOrganizationMentionOccurrence.occurrence_order)
            )
        ).all()
        assert len(occ) == 2
        assert occ[0].mention_text.startswith("Chicago City Hall")
        assert occ[0].quote_text is None
        assert occ[1].quote_text == occ[1].mention_text
        assert "quote" in occ[1].labels_json


def test_persist_empty_organizations_array_is_noop() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-oe", project_slug="proj-oe")
        session.add(AgateRun(id="run-oe", graph_id="graph-oe", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-oe",
            run_id="run-oe",
            consolidated={
                "text": "No organizations here.",
                "url": "https://example.com/no-orgs",
                "organizations": [],
            },
        )
        session.commit()

        org_summaries = [s for s in result.domain_summaries if s.domain == "organizations"]
        assert len(org_summaries) == 1
        assert org_summaries[0].added == 0

    with Session(engine) as session:
        assert session.exec(select(SubstrateOrganization)).all() == []


def test_persist_organizations_only_without_places_or_people() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-oo", project_slug="proj-oo")
        session.add(AgateRun(id="run-oo", graph_id="graph-oo", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-oo",
            run_id="run-oo",
            consolidated={
                "text": "Chicago City Hall spoke at the rally.",
                "url": "https://example.com/orgs-only",
                "organizations": [_sample_organization_entry()],
            },
        )
        session.commit()

        assert result.reconciliation_summary.domain == "organizations"
        assert result.reconciliation_summary.added == 1

    with Session(engine) as session:
        assert len(session.exec(select(SubstrateOrganization)).all()) == 1


def test_organizations_reingest_retires_stale_system_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    url = "https://example.com/orgs-rerun"

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-or", project_slug="proj-or")
        session.add(AgateRun(id="run-or1", graph_id="graph-or", status="pending"))
        session.add(AgateRun(id="run-or2", graph_id="graph-or", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-or",
            run_id="run-or1",
            consolidated={
                "text": "Chicago City Hall and Cook County attended.",
                "url": url,
                "organizations": [
                    _sample_organization_entry(name="Chicago City Hall"),
                    _sample_organization_entry(name="Cook County"),
                ],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        old_county = session.exec(
            select(SubstrateOrganization).where(
                SubstrateOrganization.normalized_name == "cook county"
            )
        ).one()
        old_county_id = int(old_county.id)  # type: ignore[arg-type]
        county_mention = session.exec(
            select(SubstrateOrganizationMention).where(
                SubstrateOrganizationMention.organization_id == old_county_id,
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
            )
        ).one()
        county_occ = session.exec(
            select(SubstrateOrganizationMentionOccurrence).where(
                SubstrateOrganizationMentionOccurrence.organization_mention_id
                == int(county_mention.id)
            )
        ).first()
        assert county_occ is not None
        session.add(
            SubstrateOrganizationSemanticDocument(
                project_id=project_id,
                article_id=int(county_mention.article_id),
                organization_id=old_county_id,
                organization_mention_id=int(county_mention.id),
                organization_mention_occurrence_id=int(county_occ.id),
                search_text="Cook County",
                source_hash="hash-county-sem",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )
        session.commit()

        _, retired, disposed, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-or",
            run_id="run-or2",
            consolidated={
                "text": "Chicago City Hall attended alone.",
                "url": url,
                "organizations": [_sample_organization_entry(name="Chicago City Hall")],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

    assert retired == 1
    assert disposed == 1

    with Session(engine) as session:
        assert session.get(SubstrateOrganization, old_county_id) is None
        active_mentions = session.exec(
            select(SubstrateOrganizationMention).where(
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        ).all()
        assert len(active_mentions) == 1


def _mock_organizations_demo_json() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "Chicago City Hall",
                    "type": "government",
                    "role_in_story": "Announced park initiative",
                    "nature": "actor",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Chicago City Hall announced a new park initiative Monday.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Police Department",
                    "type": "law_enforcement",
                    "role_in_story": "Will increase patrols",
                    "nature": "regulator",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "The Chicago Police Department said it will increase "
                                "patrols near the site."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Cook County",
                    "type": "government",
                    "role_in_story": "Approved funding",
                    "nature": "source",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Cook County approved funding for the project.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Cubs",
                    "type": "sports_team",
                    "role_in_story": "Hosted ribbon-cutting",
                    "nature": "context",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "The Chicago Cubs hosted a ribbon-cutting at Wrigley Field."
                            ),
                            "quote": False,
                        }
                    ],
                },
            ]
        }
    )


def test_organization_extract_pipeline_persist_to_substrate() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-oe2", project_slug="proj-oe2")
        session.add(AgateRun(id="run-oe2", graph_id="graph-oe2", status="pending"))
        session.commit()

        spec = starter_organizations_flow_graph_spec()
        with patch(
            "agate_nodes.organization_extract.node_port.call_llm",
            return_value=_mock_organizations_demo_json(),
        ):
            out = execute_graph(spec)
        body = out["stylebook_output"]
        assert body["success"] is True
        assert len(body["organizations"]) >= 4

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-oe2",
            run_id="run-oe2",
            consolidated=body,
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

    with Session(engine) as session:
        orgs = session.exec(select(SubstrateOrganization)).all()
        assert len(orgs) >= 4
        mentions = session.exec(select(SubstrateOrganizationMention)).all()
        assert len(mentions) >= 4
        natures = {m.nature for m in mentions if m.nature}
        assert "actor" in natures
        assert "regulator" in natures
