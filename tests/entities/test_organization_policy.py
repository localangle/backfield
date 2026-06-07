"""Organization policy and LLM adjudication tests."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.canonical.plan_types import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.organization import AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate.entities.organization.adjudication import (
    adjudicate_ambiguous_organization_plan_with_llm,
)


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-organization-policy")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-org-policy", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_adjudicate_ambiguous_organization_upgrades_when_llm_confident(monkeypatch) -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        c1 = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Police Department",
            slug="cpd",
            organization_type="law_enforcement",
        )
        c2 = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Park District Police",
            slug="cppd",
            organization_type="law_enforcement",
        )
        session.add(c1)
        session.add(c2)
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        id1 = str(c1.id)
        id2 = str(c2.id)

        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Police Department",
            normalized_name="chicago police department",
            organization_type="law_enforcement",
            identity_fingerprint="fp-org-adj",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH,
                    "recall_canonical_ids": [id1, id2],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{id1}", "confidence": {ADJUDICATION_LINK_MIN_CONFIDENCE}, '
                f'"rationale": "Same police department."}}'
            )

        monkeypatch.setattr(
            "worker.substrate.entities.organization.adjudication.call_llm",
            _fake_llm,
        )

        out = adjudicate_ambiguous_organization_plan_with_llm(
            session,
            plan=plan,
            organization=organization,
            stylebook_id=sb_id,
            model="gpt-4o-mini",
        )
        assert out.decision == CanonicalPersistDecision.LINK_EXISTING
        assert out.existing_canonical_id == id1


def test_adjudicate_ambiguous_organization_materializes_when_llm_rejects_link(
    monkeypatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        c1 = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Teachers Union",
            slug="ctu",
            organization_type="community_group",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Teachers Union",
            normalized_name="chicago teachers union",
            organization_type="community_group",
            identity_fingerprint="fp-org-adj-2",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return '{"canonical_id": null, "confidence": 0.2, "rationale": "Uncertain."}'

        monkeypatch.setattr(
            "worker.substrate.entities.organization.adjudication.call_llm",
            _fake_llm,
        )

        out = adjudicate_ambiguous_organization_plan_with_llm(
            session,
            plan=plan,
            organization=organization,
            stylebook_id=sb_id,
            model="gpt-4o-mini",
        )
        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
