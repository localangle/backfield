"""Organization canonical recall (alias-first, capped candidates)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.entities.organization import (
    ORGANIZATION_RECALL_DEFAULT_LIMIT,
    organization_strong_identity_matches_canonical,
    retrieve_organization_canonical_candidates,
    upsert_alias_for_canonical_text,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-organization-recall")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-org-recall", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_organization_strong_identity_requires_matching_type() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Police Department",
            slug="chicago-police-department",
            organization_type="law_enforcement",
        )
        session.add(canon)
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Police Department",
            normalized_name="chicago police department",
            organization_type="company",
        )
        assert not organization_strong_identity_matches_canonical(organization, canon)


def test_recall_caps_at_default_limit() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        for i in range(30):
            session.add(
                StylebookOrganizationCanonical(
                    stylebook_id=sb_id,
                    label=f"Metro Agency {i}",
                    slug=f"metro-agency-{i}",
                    organization_type="government",
                )
            )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Metro Agency 1",
            normalized_name="metro agency 1",
            organization_type="government",
        )
        recall = retrieve_organization_canonical_candidates(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert len(recall) <= ORGANIZATION_RECALL_DEFAULT_LIMIT
        assert len(recall) > 0


def test_recall_ranks_exact_alias_match() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Teachers Union",
            slug="chicago-teachers-union",
            organization_type="community_group",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="CTU",
            normalized_alias="ctu",
            provenance="seed",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="CTU",
            normalized_name="ctu",
            organization_type="community_group",
        )
        recall = retrieve_organization_canonical_candidates(
            session,
            stylebook_id=sb_id,
            organization=organization,
            limit=8,
        )
        labels = [label for _cid, label in recall]
        assert "Chicago Teachers Union" in labels
