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
from backfield_entities.entities.organization.policy import ORGANIZATION_CANONICAL_TYPE_MISMATCH
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate.entities.organization.adjudication import (
    adjudicate_ambiguous_organization_plan_with_llm,
)


def _adj_json_link(canonical_id: str, confidence: float, rationale: str) -> str:
    return (
        f'{{"decision": "link_existing", "canonical_id": "{canonical_id}", '
        f'"confidence": {confidence}, "same_identity": true, '
        f'"conflicting_identity_evidence": false, "rationale": "{rationale}"}}'
    )


def _adj_json_reject(confidence: float, rationale: str, *, decision: str = "no_match") -> str:
    return (
        f'{{"decision": "{decision}", "canonical_id": null, '
        f'"confidence": {confidence}, "same_identity": false, '
        f'"conflicting_identity_evidence": true, "rationale": "{rationale}"}}'
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
            return _adj_json_link(
                id1, ADJUDICATION_LINK_MIN_CONFIDENCE, "Same police department."
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
            return _adj_json_reject(0.2, "Uncertain.", decision="uncertain")

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


def test_adjudicate_type_mismatch_links_cross_type_when_llm_confident(monkeypatch) -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago",
            slug="chicago-city",
            organization_type="government",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        canon_id = str(canon.id)

        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago",
            normalized_name="chicago",
            organization_type="sports_team",
            identity_fingerprint="fp-org-type-mismatch",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": ORGANIZATION_CANONICAL_TYPE_MISMATCH,
                    "canonical_id": canon_id,
                    "recall_canonical_ids": [canon_id],
                    "substrate_type": "sports_team",
                    "canonical_type": "government",
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return _adj_json_link(
                canon_id,
                ADJUDICATION_LINK_MIN_CONFIDENCE,
                "Same city government despite sports_team label.",
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
        assert out.existing_canonical_id == canon_id


def test_adjudicate_compatible_type_mismatch_links_at_lower_confidence(monkeypatch) -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Brutalist Brewing",
            slug="brutalist-brewing",
            organization_type="company",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        canon_id = str(canon.id)

        organization = SubstrateOrganization(
            project_id=pid,
            name="Brutalist Brewing",
            normalized_name="brutalist brewing",
            organization_type="local_business",
            identity_fingerprint="fp-brewery-type-mismatch",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": ORGANIZATION_CANONICAL_TYPE_MISMATCH,
                    "canonical_id": canon_id,
                    "recall_canonical_ids": [canon_id],
                    "substrate_type": "local_business",
                    "canonical_type": "company",
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return _adj_json_link(
                canon_id,
                0.82,
                "Same brewery; local_business vs company is a labeling difference.",
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
        assert out.existing_canonical_id == canon_id
