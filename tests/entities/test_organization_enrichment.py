"""Organization enrichment cache reuse and empty-only metadata writes."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    SubstrateOrganization,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.entities.organization.enrichment import (
    cached_selected_links,
    fill_empty_organization_enrichment_meta,
)
from backfield_entities.entities.organization.persist import apply_canonical_persist_plan
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate.entities.organization.upsert import _upsert_organization

from tests.project_helpers import project_ownership_fields


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-organization-enrich")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    proj = BackfieldProject(
        **project_ownership_fields(session, oid),
        name="Demo",
        slug="demo-organization-enrich",
        organization_id=oid,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(sb.id), int(proj.id)  # type: ignore[arg-type]


def _canonical(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    label: str,
    slug: str,
    organization_type: str,
    links: dict[str, str],
) -> str:
    canon = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        label=label,
        slug=slug,
        organization_type=organization_type,
        status="active",
    )
    session.add(canon)
    session.commit()
    session.refresh(canon)
    canonical_id = str(canon.id)
    meta_by_key = {"wikidata_id": "wikidata", "wikipedia_url": "wikipedia"}
    for link_key, meta_type in meta_by_key.items():
        value = links.get(link_key)
        if not value:
            continue
        session.add(
            StylebookOrganizationMeta(
                project_id=project_id,
                stylebook_organization_canonical_id=canonical_id,
                meta_type=meta_type,
                value_type="text",
                value_text=value,
            )
        )
    session.commit()
    return canonical_id


def test_cached_links_reuse_a_single_complete_canonical() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Chicago Bears",
            slug="chicago-bears",
            organization_type="sports_team",
            links={
                "wikidata_id": "Q205041",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Chicago_Bears",
            },
        )
        found = cached_selected_links(
            session,
            stylebook_id=sb_id,
            name="Chicago Bears",
            organization_type="sports_team",
            sources={"wikidata", "wikipedia"},
            project_id=pid,
        )
        assert found == {
            "wikidata_id": "Q205041",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Chicago_Bears",
        }


def test_cached_links_skip_ambiguous_and_incomplete_canonicals() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="City Council",
            slug="city-council-1",
            organization_type="government",
            links={"wikidata_id": "Q1", "wikipedia_url": "https://en.wikipedia.org/wiki/One"},
        )
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="City Council",
            slug="city-council-2",
            organization_type="government",
            links={"wikidata_id": "Q2", "wikipedia_url": "https://en.wikipedia.org/wiki/Two"},
        )
        assert (
            cached_selected_links(
                session,
                stylebook_id=sb_id,
                name="City Council",
                organization_type="government",
                sources={"wikidata", "wikipedia"},
                project_id=pid,
            )
            is None
        )
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Chicago Bulls",
            slug="chicago-bulls",
            organization_type="sports_team",
            links={"wikidata_id": "Q128109"},
        )
        assert (
            cached_selected_links(
                session,
                stylebook_id=sb_id,
                name="Chicago Bulls",
                organization_type="sports_team",
                sources={"wikidata", "wikipedia"},
                project_id=pid,
            )
            is None
        )
        assert cached_selected_links(
            session,
            stylebook_id=sb_id,
            name="Chicago Bulls",
            organization_type="sports_team",
            sources={"wikidata"},
            project_id=pid,
        ) == {"wikidata_id": "Q128109"}


def test_meta_fill_does_not_overwrite_existing_text() -> None:
    engine = _engine()
    with Session(engine) as session:
        _sb_id, pid = _seed(session)
        canonical_id = _canonical(
            session,
            stylebook_id=_sb_id,
            project_id=pid,
            label="Chicago Bears",
            slug="chicago-bears",
            organization_type="sports_team",
            links={"wikidata_id": "QOLD"},
        )
        fill_empty_organization_enrichment_meta(
            session,
            project_id=pid,
            canonical_id=canonical_id,
            links={
                "wikidata_id": "QNEW",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Chicago_Bears",
            },
        )
        session.commit()
        rows = session.exec(
            select(StylebookOrganizationMeta).where(
                StylebookOrganizationMeta.stylebook_organization_canonical_id == canonical_id
            )
        ).all()
        by_type = {row.meta_type: row.value_text for row in rows}
        assert by_type["wikidata"] == "QOLD"
        assert by_type["wikipedia"] == "https://en.wikipedia.org/wiki/Chicago_Bears"


def test_materialize_copies_links_onto_empty_metadata() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        organization = SubstrateOrganization(
            project_id=pid,
            name="New Club",
            normalized_name="new club",
            organization_type="sports_team",
            source_details_json={
                "wikidata_id": "Q123",
                "wikipedia_url": "https://en.wikipedia.org/wiki/New_Club",
            },
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)
        apply_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
            plan=CanonicalPersistPlan(decision=CanonicalPersistDecision.MATERIALIZE_NEW),
            organizations_bucket="ready",
        )
        session.commit()
        session.refresh(organization)
        canonical_id = str(organization.stylebook_organization_canonical_id)
        rows = session.exec(
            select(StylebookOrganizationMeta).where(
                StylebookOrganizationMeta.stylebook_organization_canonical_id == canonical_id
            )
        ).all()
        by_type = {row.meta_type: row.value_text for row in rows}
        assert by_type["wikidata"] == "Q123"
        assert by_type["wikipedia"] == "https://en.wikipedia.org/wiki/New_Club"


def test_upsert_stores_links_and_keeps_them_when_a_later_entry_omits_them() -> None:
    engine = _engine()
    with Session(engine) as session:
        _sb_id, pid = _seed(session)
        entry = {
            "name": "Chicago Bears",
            "type": "sports_team",
            "wikidata_id": "Q205041",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Chicago_Bears",
        }
        created = _upsert_organization(
            session,
            project_id=pid,
            bucket="ready",
            entry=entry,
            run_id="run-1",
            graph_id="graph-1",
        )
        assert created is not None
        session.commit()
        details = created.organization.source_details_json
        assert isinstance(details, dict)
        assert details["wikidata_id"] == "Q205041"
        assert details["wikipedia_url"] == "https://en.wikipedia.org/wiki/Chicago_Bears"

        again = _upsert_organization(
            session,
            project_id=pid,
            bucket="ready",
            entry={"name": "Chicago Bears", "type": "sports_team"},
            run_id="run-2",
            graph_id="graph-1",
            update_existing=True,
        )
        assert again is not None
        session.commit()
        session.refresh(again.organization)
        kept = again.organization.source_details_json
        assert isinstance(kept, dict)
        assert kept["wikidata_id"] == "Q205041"
        assert kept["wikipedia_url"] == "https://en.wikipedia.org/wiki/Chicago_Bears"
