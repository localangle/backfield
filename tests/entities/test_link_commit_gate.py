"""Sync link commit gate and trusted-alias quarantine."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.canonical.link_commit_gate import (
    VETO_CANONICAL_INACTIVE,
    VETO_CANONICAL_SELF_INCONSISTENT,
    VETO_OBVIOUS_NAME_MISMATCH,
    coerce_blocked_link_plan,
    sync_link_commit_blocked,
)
from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.location.persist import refresh_aliases_for_linked_location
from backfield_entities.entities.organization.recall import (
    canonical_ids_from_organization_name_keys,
)
from backfield_entities.entities.person.recall import canonical_ids_from_person_name_keys
from backfield_entities.entities.person.types import normalize_person_text
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-link-commit-gate")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(
        organization_id=oid,
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    proj = BackfieldProject(name="Demo", slug="demo-link-commit-gate", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(sb.id), int(proj.id)  # type: ignore[arg-type]


def test_sync_gate_blocks_kam_jones_to_tre_jones() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Tre Jones",
            slug="tre-jones",
        )
        session.add(canon)
        session.flush()
        person = SubstratePerson(
            project_id=project_id,
            name="Kam Jones",
            normalized_name=normalize_person_text("Kam Jones"),
            canonical_link_status="pending",
        )
        session.add(person)
        session.commit()
        assert canon.id is not None

        veto = sync_link_commit_blocked(
            session,
            entity_type="person",
            substrate_row=person,
            canonical_id=str(canon.id),
            stylebook_id=sb_id,
        )
        assert veto == VETO_OBVIOUS_NAME_MISMATCH

        coerced = coerce_blocked_link_plan(
            CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=str(canon.id),
            ),
            entity_type="person",
            substrate_row=person,
            veto_code=veto,
        )
        assert coerced.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        assert any(
            isinstance(r, dict) and r.get("code") == "sync_link_commit_veto"
            for r in coerced.resolution_reasons
        )


def test_sync_gate_blocks_university_of_maryland_to_umn_duluth() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="University of Minnesota Duluth",
            slug="university-of-minnesota-duluth",
            organization_type="school",
        )
        session.add(canon)
        session.flush()
        org = SubstrateOrganization(
            project_id=project_id,
            name="University of Maryland",
            normalized_name="university of maryland",
            organization_type="school",
            canonical_link_status="pending",
        )
        session.add(org)
        session.commit()
        assert canon.id is not None

        veto = sync_link_commit_blocked(
            session,
            entity_type="organization",
            substrate_row=org,
            canonical_id=str(canon.id),
            stylebook_id=sb_id,
        )
        assert veto == VETO_OBVIOUS_NAME_MISMATCH


@pytest.mark.parametrize(
    ("case", "expected_veto"),
    [
        ("inactive", VETO_CANONICAL_INACTIVE),
        ("geometry_mismatch", VETO_CANONICAL_SELF_INCONSISTENT),
        ("jurisdiction_mismatch", VETO_CANONICAL_SELF_INCONSISTENT),
        ("named_poi_contradiction", VETO_CANONICAL_SELF_INCONSISTENT),
        ("consistent", None),
    ],
)
def test_location_commit_gate_revalidates_canonical_self_consistency(
    case: str,
    expected_veto: str | None,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        canonical = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Harbor Arts Center, Chicago, IL",
            slug=f"harbor-arts-{case}",
            location_type="place",
            country_code="US",
            subdivision_code="IL",
            status="inactive" if case == "inactive" else "active",
            formatted_address=(
                "Harbor Arts Center, Chicago, IN, USA"
                if case == "jurisdiction_mismatch"
                else "Other Pavilion, Chicago, IL, USA"
                if case == "named_poi_contradiction"
                else "Harbor Arts Center, Chicago, IL, USA"
            ),
            geometry_type="Polygon" if case == "geometry_mismatch" else "Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
        )
        session.add(canonical)
        session.flush()
        location = SubstrateLocation(
            project_id=project_id,
            name="Harbor Arts Center, Chicago, IL",
            normalized_name="harbor arts center, chicago, il",
            location_type="place",
            status="resolved",
            canonical_link_status="pending",
            formatted_address="Harbor Arts Center, Chicago, IL, USA",
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
            source_details_json={
                "place_extract_components": {
                    "place": {"name": "Harbor Arts Center"},
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
        )
        session.add(location)
        session.commit()

        veto = sync_link_commit_blocked(
            session,
            entity_type="location",
            substrate_row=location,
            canonical_id=str(canonical.id),
            stylebook_id=sb_id,
            entry={"components": location.source_details_json["place_extract_components"]},
        )
        assert veto == expected_veto


def test_linked_location_refresh_revalidates_parent_child_identity() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        parent = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Harbor Arts Center, Chicago, IL",
            slug="harbor-arts-parent",
            location_type="place",
            country_code="US",
            subdivision_code="IL",
            status="active",
            formatted_address="Harbor Arts Center, Chicago, IL, USA",
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
        )
        session.add(parent)
        session.flush()
        child = SubstrateLocation(
            project_id=project_id,
            name="Harbor Arts Center Annex, Chicago, IL",
            normalized_name="harbor arts center annex, chicago, il",
            location_type="place",
            status="resolved",
            canonical_link_status="linked",
            stylebook_location_canonical_id=str(parent.id),
            formatted_address="Harbor Arts Center Annex, Chicago, IL, USA",
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
            source_details_json={
                "place_extract_components": {
                    "place": {"name": "Harbor Arts Center Annex"},
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
        )
        session.add(child)
        session.commit()

        refresh_aliases_for_linked_location(
            session,
            stylebook_id=sb_id,
            location=child,
        )
        session.flush()
        aliases = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(parent.id)
            )
        ).all()
        assert aliases == []


def test_trusted_alias_only_excludes_substrate_ingest_person_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _project_id = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Tre Jones",
            slug="tre-jones-alias",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        session.add(
            StylebookPersonAlias(
                person_canonical_id=str(canon.id),
                alias_text="Kam Jones",
                normalized_alias=normalize_person_text("Kam Jones"),
                provenance="substrate_ingest",
                suppressed=False,
            )
        )
        session.commit()

        untrusted = canonical_ids_from_person_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Kam Jones",
            trusted_alias_only=False,
        )
        trusted = canonical_ids_from_person_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Kam Jones",
            trusted_alias_only=True,
        )
        assert untrusted == [str(canon.id)]
        assert trusted == []


def test_trusted_alias_only_keeps_editorial_organization_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _project_id = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="University of Minnesota Duluth",
            slug="umd-editorial",
            organization_type="school",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(canon.id),
                alias_text="UMD",
                normalized_alias="umd",
                provenance="stylebook_ui_accept",
                suppressed=False,
            )
        )
        session.commit()

        trusted = canonical_ids_from_organization_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="UMD",
            trusted_alias_only=True,
        )
        assert trusted == [str(canon.id)]
