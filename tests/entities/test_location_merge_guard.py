"""Tests for the location merge type/identity guard and alias variant pruning."""

from __future__ import annotations

from uuid import uuid4

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.entities.linking.substrate_actions import (
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.location.merge import merge_location_canonical_into
from backfield_entities.entities.location.persist import upsert_alias_for_canonical_text
from backfield_entities.geo.geometry_bind import assign_geojson_geometry
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _seed(session: Session, *, slug: str) -> tuple[int, int, int]:
    org = BackfieldOrganization(name="Org", slug=slug)
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, org_id)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    proj = BackfieldProject(
        **project_ownership_fields(session, org_id),
        name="News",
        slug="news",
        organization_id=org_id,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]
    return org_id, stylebook_id, project_id


def _canonical(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    slug: str,
    location_type: str,
) -> StylebookLocationCanonical:
    canon = StylebookLocationCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label=label,
        slug=slug,
        location_type=location_type,
    )
    session.add(canon)
    session.commit()
    return canon


def test_merge_venue_place_into_city_is_blocked() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, _project_id = _seed(session, slug="org-merge-guard-block")
        city = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
        )
        venue = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Perman, Chicago, IL",
            slug="perman-chicago-il",
            location_type="place",
        )
        with pytest.raises(ValueError, match="different kinds of places"):
            merge_location_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
                source_canonical_id=str(venue.id),
                target_canonical_id=str(city.id),
            )


def test_merge_same_type_places_still_allowed() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, _project_id = _seed(session, slug="org-merge-guard-allow")
        keeper = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago Shakespeare Theater, Chicago, IL",
            slug="chicago-shakespeare-theater",
            location_type="place",
        )
        dupe = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago Shakespeare Theatre, Chicago, IL",
            slug="chicago-shakespeare-theatre",
            location_type="place",
        )
        result = merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            source_canonical_id=str(dupe.id),
            target_canonical_id=str(keeper.id),
        )
        assert result.source_deleted is True
        source_alias = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(keeper.id),
                StylebookLocationAlias.normalized_alias
                == "chicago shakespeare theatre, chicago, il",
            )
        ).first()
        assert source_alias is not None
        assert source_alias.provenance == "stylebook_cleanup_merge"
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(keeper.id),
            alias_text="Chicago Shakespeare Theatre, Chicago, IL",
            normalized_alias="chicago shakespeare theatre, chicago, il",
            provenance="substrate_ingest",
        )
        session.flush()
        session.refresh(source_alias)
        assert source_alias.provenance == "stylebook_cleanup_merge"


def test_merge_preserves_source_geography_when_target_has_none() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, _project_id = _seed(
            session,
            slug="org-merge-preserve-geography",
        )
        keeper = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Latin America",
            slug="latin-america",
            location_type="region",
        )
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="América Latina",
            slug="america-latina",
            location_type="region",
        )
        source.formatted_address = "Latin America"
        source.country_code = "ZZ"
        assign_geojson_geometry(
            session,
            source,
            {"type": "Point", "coordinates": [-75.0, -10.0]},
        )
        session.commit()

        merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(keeper.id),
        )
        session.flush()
        session.refresh(keeper)

        assert keeper.geometry_json == {
            "type": "Point",
            "coordinates": [-75.0, -10.0],
        }
        assert keeper.formatted_address == "Latin America"
        assert keeper.country_code == "ZZ"


def test_merge_same_label_cross_type_still_allowed() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, _project_id = _seed(session, slug="org-merge-guard-identity")
        keeper = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Near North Side, Chicago, IL",
            slug="near-north-side",
            location_type="neighborhood",
        )
        mistyped = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Near North Side, Chicago, IL",
            slug="near-north-side-2",
            location_type="place",
        )
        result = merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            source_canonical_id=str(mistyped.id),
            target_canonical_id=str(keeper.id),
        )
        assert result.source_deleted is True


def test_unlink_prunes_all_alias_variants() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session, slug="org-alias-prune")
        city = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
        )
        substrate = SubstrateLocation(
            project_id=project_id,
            name="Perman, Chicago, IL",
            normalized_name="perman, chicago, il",
            location_type="place",
            stylebook_location_canonical_id=str(city.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        session.add(substrate)
        # Both the exact and loose (comma-less) variants, as merge/relink writes them.
        for norm in ("perman, chicago, il", "perman chicago il"):
            session.add(
                StylebookLocationAlias(
                    location_canonical_id=str(city.id),
                    alias_text="Perman, Chicago, IL",
                    normalized_alias=norm,
                    provenance="stylebook_cleanup_merge",
                    suppressed=False,
                )
            )
        session.commit()
        session.refresh(substrate)

        unlink_substrate_from_canonical(
            session,
            stylebook_id=stylebook_id,
            location=substrate,
        )
        session.commit()

        remaining = session.exec(
            select(StylebookLocationAlias.normalized_alias).where(
                StylebookLocationAlias.location_canonical_id == str(city.id)
            )
        ).all()
        assert "perman, chicago, il" not in remaining
        assert "perman chicago il" not in remaining
