"""Merge semantics the cleanup API relies on, from the places and people case studies.

Each test names the merge fix it covers (see docs/plan/stylebook-cleanup-api.md, "Shared merge
fixes"). They run the real merge functions on SQLite.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.entities.location.merge import merge_location_canonical_into
from backfield_entities.entities.organization.merge import merge_organization_canonical_into
from backfield_entities.entities.person.merge import merge_person_canonical_into
from backfield_entities.geo.geometry_bind import assign_geojson_geometry
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _session() -> Session:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session) -> tuple[int, int, int]:
    """Return organization id, Stylebook id, and project id."""
    organization = BackfieldOrganization(name="Org", slug=f"org-merge-semantics-{uuid4().hex}")
    session.add(organization)
    session.commit()
    organization_id = int(organization.id)  # type: ignore[arg-type]
    stylebook = Stylebook(
        organization_id=organization_id, slug="default", name="Default", is_default=True
    )
    session.add(stylebook)
    session.commit()
    session.refresh(stylebook)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    project = BackfieldProject(
        **project_ownership_fields(session, organization_id, stylebook_id=stylebook_id),
        name="Demo",
        slug=f"demo-merge-semantics-{uuid4().hex}",
        organization_id=organization_id,
        stylebook_id=stylebook_id,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return organization_id, stylebook_id, int(project.id)  # type: ignore[arg-type]


def _location(
    session: Session, *, stylebook_id: int, label: str, location_type: str = "place"
) -> StylebookLocationCanonical:
    row = StylebookLocationCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label=label,
        slug=f"{label.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        location_type=location_type,
    )
    session.add(row)
    session.flush()
    return row


def _location_alias(
    canonical_id: str, text: str, normalized: str, provenance: str, *, suppressed: bool = False
) -> StylebookLocationAlias:
    return StylebookLocationAlias(
        location_canonical_id=canonical_id,
        alias_text=text,
        normalized_alias=normalized,
        provenance=provenance,
        suppressed=suppressed,
    )


def _open_connection(
    *, project_id: int, stylebook_id: int, from_id: str, to_id: str, entity_type: str
) -> StylebookConnection:
    return StylebookConnection(
        project_id=project_id,
        stylebook_id=stylebook_id,
        from_entity_type=entity_type,
        from_entity_id=from_id,
        to_entity_type=entity_type,
        to_entity_id=to_id,
        nature="related_to",
    )


# --- Fix 1: connections move to the survivor, even when relinking prunes the source ----------


def test_location_merge_keeps_connections_open_when_source_is_pruned_during_relink() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Wrigley Fld, Chicago, IL")
        target = _location(session, stylebook_id=stylebook_id, label="Wrigley Field, Chicago, IL")
        neighbor = _location(session, stylebook_id=stylebook_id, label="Wrigleyville, Chicago, IL")
        # An ingest-only source: relinking its last substrate prunes it.
        session.add_all(
            [
                SubstrateLocation(
                    project_id=project_id,
                    name="Wrigley Fld, Chicago, IL",
                    normalized_name="wrigley fld, chicago, il",
                    location_type="place",
                    stylebook_location_canonical_id=str(source.id),
                    canonical_link_status="linked",
                ),
                _location_alias(
                    str(source.id),
                    "Wrigley Fld, Chicago, IL",
                    "wrigley fld, chicago, il",
                    "substrate_ingest",
                ),
                _open_connection(
                    project_id=project_id,
                    stylebook_id=stylebook_id,
                    from_id=str(source.id),
                    to_id=str(neighbor.id),
                    entity_type="location",
                ),
            ]
        )
        session.commit()

        merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        connection = session.exec(select(StylebookConnection)).one()
        assert connection.from_entity_id == str(target.id)
        assert connection.closed_at is None


def test_organization_merge_keeps_connections_open_when_source_is_pruned_during_relink() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id, label="Acme Corp", slug=f"acme-corp-{uuid4().hex[:6]}"
        )
        target = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id, label="Acme Corporation", slug=f"acme-{uuid4().hex[:6]}"
        )
        neighbor = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id, label="Acme Foundation", slug=f"foundation-{uuid4().hex[:6]}"
        )
        session.add_all([source, target, neighbor])
        session.flush()
        session.add_all(
            [
                SubstrateOrganization(
                    project_id=project_id,
                    name="Acme Corp",
                    normalized_name="acme corp",
                    stylebook_organization_canonical_id=str(source.id),
                    canonical_link_status="linked",
                ),
                StylebookOrganizationAlias(
                    organization_canonical_id=str(source.id),
                    alias_text="Acme Corp",
                    normalized_alias="acme corp",
                    provenance="substrate_ingest",
                    suppressed=False,
                ),
                _open_connection(
                    project_id=project_id,
                    stylebook_id=stylebook_id,
                    from_id=str(source.id),
                    to_id=str(neighbor.id),
                    entity_type="organization",
                ),
            ]
        )
        session.commit()

        merge_organization_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        connection = session.exec(select(StylebookConnection)).one()
        assert connection.from_entity_id == str(target.id)
        assert connection.closed_at is None


def test_person_merge_keeps_connections_open_when_source_is_pruned_during_relink() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = StylebookPersonCanonical(
            stylebook_id=stylebook_id, label="Jon Smith", slug=f"jon-{uuid4().hex[:6]}"
        )
        target = StylebookPersonCanonical(
            stylebook_id=stylebook_id, label="John Smith", slug=f"john-{uuid4().hex[:6]}"
        )
        neighbor = StylebookPersonCanonical(
            stylebook_id=stylebook_id, label="Jane Smith", slug=f"jane-{uuid4().hex[:6]}"
        )
        session.add_all([source, target, neighbor])
        session.flush()
        session.add_all(
            [
                SubstratePerson(
                    project_id=project_id,
                    name="Jon Smith",
                    normalized_name="jon smith",
                    stylebook_person_canonical_id=str(source.id),
                    canonical_link_status="linked",
                ),
                StylebookPersonAlias(
                    person_canonical_id=str(source.id),
                    alias_text="Jon Smith",
                    normalized_alias="jon smith",
                    provenance="substrate_ingest",
                    suppressed=False,
                ),
                _open_connection(
                    project_id=project_id,
                    stylebook_id=stylebook_id,
                    from_id=str(source.id),
                    to_id=str(neighbor.id),
                    entity_type="person",
                ),
            ]
        )
        session.commit()

        merge_person_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        connection = session.exec(select(StylebookConnection)).one()
        assert connection.from_entity_id == str(target.id)
        assert connection.closed_at is None


# --- Fix 2: every source alias and the source label reach the survivor, survivor aliases stay --


def test_location_merge_carries_source_aliases_and_keeps_survivor_aliases() -> None:
    with _session() as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Trocadero, Paris, France")
        target = _location(session, stylebook_id=stylebook_id, label="Trocadéro, Paris, France")
        session.add_all(
            [
                _location_alias(
                    str(source.id), "Place du Trocadéro", "place du trocadéro", "stylebook_manual"
                ),
                _location_alias(
                    str(source.id), "Trocadero plaza", "trocadero plaza", "substrate_ingest"
                ),
                # The survivor already holds the source label as a suppressed, reviewed alias.
                _location_alias(
                    str(target.id),
                    "Trocadero, Paris, France",
                    "trocadero, paris, france",
                    "stylebook_ui_manual",
                    suppressed=True,
                ),
            ]
        )
        session.commit()

        merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            provenance="stylebook_cleanup_test",
        )
        session.commit()

        aliases = {
            row.normalized_alias: row
            for row in session.exec(
                select(StylebookLocationAlias).where(
                    StylebookLocationAlias.location_canonical_id == str(target.id)
                )
            ).all()
        }
        assert aliases["place du trocadéro"].provenance == "stylebook_cleanup_test"
        assert aliases["trocadero plaza"].provenance == "stylebook_cleanup_test"
        survivor_alias = aliases["trocadero, paris, france"]
        assert survivor_alias.suppressed is True
        assert survivor_alias.provenance == "stylebook_ui_manual"


# --- Fix 3: never drop geography or metadata silently ------------------------------------------


def _with_point(
    session: Session, canonical: StylebookLocationCanonical, coordinates: list[float]
) -> None:
    assign_geojson_geometry(session, canonical, {"type": "Point", "coordinates": coordinates})
    session.flush()


def test_location_merge_reports_source_geography_it_did_not_apply() -> None:
    with _session() as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Grant Park, Chicago, IL")
        target = _location(session, stylebook_id=stylebook_id, label="Grant Park, Chicago, IL")
        _with_point(session, source, [-87.62, 41.87])
        _with_point(session, target, [-87.63, 41.88])
        session.commit()

        result = merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        merged = session.get(StylebookLocationCanonical, str(target.id))
        assert merged is not None and merged.geometry_json["coordinates"] == [-87.63, 41.88]
        assert result.unapplied_source_geometry == {"type": "Point", "coordinates": [-87.62, 41.87]}


def test_location_merge_lets_the_caller_choose_the_source_geography() -> None:
    with _session() as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Grant Park, Chicago, IL")
        target = _location(session, stylebook_id=stylebook_id, label="Grant Park, Chicago, IL")
        _with_point(session, source, [-87.62, 41.87])
        _with_point(session, target, [-87.63, 41.88])
        session.commit()

        result = merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            geometry_winner="source",
        )
        session.commit()

        merged = session.get(StylebookLocationCanonical, str(target.id))
        assert merged is not None and merged.geometry_json["coordinates"] == [-87.62, 41.87]
        assert result.unapplied_source_geometry is None


def test_location_merge_carries_source_metadata_and_refuses_conflicts() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Navy Pier, Chicago, IL")
        target = _location(session, stylebook_id=stylebook_id, label="Navy Pier, Chicago, IL")
        session.add(
            StylebookLocationMeta(
                project_id=project_id,
                stylebook_location_canonical_id=str(source.id),
                meta_type="wikidata",
                value_type="text",
                value_text="Q1",
            )
        )
        session.commit()

        result = merge_location_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()
        assert result.transferred_meta_count == 1
        meta = session.exec(select(StylebookLocationMeta)).one()
        assert meta.stylebook_location_canonical_id == str(target.id)

    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _location(session, stylebook_id=stylebook_id, label="Navy Pier, Chicago, IL")
        target = _location(session, stylebook_id=stylebook_id, label="Navy Pier, Chicago, IL")
        for canonical, value in ((source, "Q1"), (target, "Q2")):
            session.add(
                StylebookLocationMeta(
                    project_id=project_id,
                    stylebook_location_canonical_id=str(canonical.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text=value,
                )
            )
        session.commit()
        with pytest.raises(ValueError, match="metadata conflict"):
            merge_location_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            )


# --- Fix 9: the shared guard refuses mixed kinds -----------------------------------------------


@pytest.mark.parametrize(
    ("source_label", "source_type", "target_label", "target_type"),
    [
        # One place with the wrong kind: fix the kind first, then merge.
        ("115 Bourbon St, New Orleans, LA", "address", "115 Bourbon St, New Orleans, LA", "place"),
        ("Near North Side, Chicago, IL", "place", "Near North Side, Chicago, IL", "neighborhood"),
        # Different places that share a name.
        ("Lincoln Park, Chicago, IL", "neighborhood", "Lincoln Park, Chicago, IL", "place"),
    ],
)
def test_location_merge_refuses_mixed_kinds_even_when_labels_match(
    source_label: str, source_type: str, target_label: str, target_type: str
) -> None:
    with _session() as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _location(
            session, stylebook_id=stylebook_id, label=source_label, location_type=source_type
        )
        target = _location(
            session, stylebook_id=stylebook_id, label=target_label, location_type=target_type
        )
        session.commit()
        with pytest.raises(ValueError, match="different kinds of places"):
            merge_location_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            )
