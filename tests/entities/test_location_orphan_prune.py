"""Ingest-orphan location canonical pruning (mirrors person/organization)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.linking.substrate_actions import (
    link_substrate_to_canonical_atomic,
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.location.persist import (
    create_standalone_canonical,
    materialize_new_canonical_and_link,
    maybe_prune_ingest_orphan_location_canonical,
)
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-location-orphan-prune")
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
        name="News",
        slug="news",
        organization_id=oid,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(sb.id), int(proj.id)  # type: ignore[arg-type]


def test_unlink_prunes_ingest_orphan_canonical_when_last_substrate_removed() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        location = SubstrateLocation(
            project_id=pid,
            name="Millennium Lakeside Garage, Chicago, IL",
            normalized_name="millennium lakeside garage, chicago, il",
            location_type="place",
            status="provisional",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(location)
        session.commit()
        session.refresh(location)

        materialize_new_canonical_and_link(session, stylebook_id=sb_id, location=location)
        session.commit()
        session.refresh(location)
        ghost_id = str(location.stylebook_location_canonical_id)
        assert ghost_id

        pruned = unlink_substrate_from_canonical(
            session,
            stylebook_id=sb_id,
            location=location,
            provenance="agate_superseded_ingest",
            requeue_after_unlink=False,
        )
        session.commit()

        assert pruned is True
        assert session.get(StylebookLocationCanonical, ghost_id) is None
        assert (
            session.exec(
                select(StylebookLocationAlias).where(
                    StylebookLocationAlias.location_canonical_id == ghost_id
                )
            ).first()
            is None
        )


def test_unlink_keeps_manual_canonical_with_zero_substrates() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Catalog Only Garage",
            provenance="stylebook_ui_manual",
        )
        session.commit()
        canon_id = str(canon.id)
        location = SubstrateLocation(
            project_id=pid,
            name="Catalog Only Garage",
            normalized_name="catalog only garage",
            location_type="place",
            status="provisional",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(location)
        session.commit()
        session.refresh(location)

        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            location=location,
            target_canonical_id=canon_id,
            provenance="stylebook_ui_link",
        )
        session.commit()
        session.refresh(location)

        pruned = unlink_substrate_from_canonical(
            session,
            stylebook_id=sb_id,
            location=location,
            provenance="stylebook_ui_unlink",
            requeue_after_unlink=True,
        )
        session.commit()

        assert pruned is False
        assert session.get(StylebookLocationCanonical, canon_id) is not None


def test_maybe_prune_skips_aliasless_legacy_canonical_without_ingest_signal() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _pid = _seed_stylebook(session)
        legacy = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Legacy Import",
            slug="legacy-import",
            location_type="place",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        legacy_id = str(legacy.id)

        pruned = maybe_prune_ingest_orphan_location_canonical(
            session,
            stylebook_id=sb_id,
            canonical_id=legacy_id,
            removed_substrate_ingest_alias=False,
        )
        session.commit()

        assert pruned is False
        assert session.get(StylebookLocationCanonical, legacy_id) is not None
