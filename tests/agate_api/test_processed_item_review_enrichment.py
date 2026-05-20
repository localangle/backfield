"""Unit tests for processed-item review enrichment."""

from __future__ import annotations

from api.processed_item_review_enrichment import (
    enrich_merged_locations_for_review,
    geometries_json_equal,
    geometry_differs_from_canonical,
)
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from sqlmodel import Session, create_engine


def test_geometries_json_equal_sorts_keys() -> None:
    a = {"type": "Point", "coordinates": [1.0, 2.0]}
    b = {"coordinates": [1.0, 2.0], "type": "Point"}
    assert geometries_json_equal(a, b)


def test_geometry_differs_from_canonical() -> None:
    saved = {"type": "Point", "coordinates": [-93.0, 45.0]}
    canon = {"type": "Point", "coordinates": [-94.0, 45.0]}
    assert geometry_differs_from_canonical(saved, canon)
    assert not geometry_differs_from_canonical(saved, saved)


def test_enrich_merged_locations_attaches_persisted_and_stylebook_link() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-enrich")
        session.add(org)
        session.commit()
        session.refresh(org)

        stylebook = Stylebook(
            organization_id=int(org.id),
            name="SB",
            slug="sb-enrich",
            is_default=True,
        )
        session.add(stylebook)
        session.commit()
        session.refresh(stylebook)

        project = BackfieldProject(
            organization_id=int(org.id),
            name="Proj",
            slug="proj-enrich",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        article = SubstrateArticle(
            project_id=int(project.id),
            headline="H",
            text="Body",
        )
        session.add(article)
        session.commit()
        session.refresh(article)

        canon_geom = {"type": "Point", "coordinates": [-93.0, 45.0]}
        saved_geom = {"type": "Point", "coordinates": [-93.1, 45.1]}
        canon = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),
            label="City Hall",
            slug="city-hall",
            geometry_json=canon_geom,
            geometry_type="Point",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        loc = SubstrateLocation(
            project_id=int(project.id),
            name="City Hall",
            normalized_name="city hall",
            location_type="address",
            stylebook_location_canonical_id=str(canon.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
            geometry_json=saved_geom,
            geometry_type="Point",
            source_details_json={"run_id": "run-1", "raw_entry_id": "L1"},
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        session.add(
            SubstrateLocationMention(
                article_id=int(article.id),
                location_id=int(loc.id),
                role_in_story="Scene of the council vote",
                nature="primary",
            )
        )
        session.commit()

        merged = [
            {
                "anchor": "L1",
                "source": "model",
                "node_id": "n1",
                "index_in_node": 0,
                "stale": False,
                "location": {
                    "id": "L1",
                    "description": "City Hall",
                    "geocode": {
                        "result": {"geometry": {"type": "Point", "coordinates": [0.0, 0.0]}},
                    },
                },
            }
        ]
        out = enrich_merged_locations_for_review(
            session,
            project_id=int(project.id),
            run_id="run-1",
            article_id=int(article.id),
            merged_locations=merged,
        )
        assert out[0]["persisted_location_id"] == int(loc.id)
        assert out[0]["stylebook_location_canonical_id"] == str(canon.id)
        assert out[0]["stylebook_slug"] == "sb-enrich"
        link = out[0]["stylebook_link"]
        assert link["label"] == "City Hall"
        assert link["has_geometry"] is True
        assert link["geometry_differs"] is True
        geom = out[0]["location"]["geocode"]["result"]["geometry"]
        assert geom["coordinates"] == [-93.1, 45.1]
        assert out[0]["location"]["role_in_story"] == "Scene of the council vote"
        assert out[0]["location"]["nature"] == "primary"


def test_enrich_skips_unlinked_canonical() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Org2", slug="org-enrich-2")
        session.add(org)
        session.commit()
        session.refresh(org)

        project = BackfieldProject(
            organization_id=int(org.id),
            name="Proj2",
            slug="proj-enrich-2",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        article = SubstrateArticle(project_id=int(project.id), headline="H", text="B")
        session.add(article)
        session.commit()
        session.refresh(article)

        loc = SubstrateLocation(
            project_id=int(project.id),
            name="Place",
            normalized_name="place",
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={"run_id": "run-2", "raw_entry_id": "p1"},
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        session.add(
            SubstrateLocationMention(
                article_id=int(article.id),
                location_id=int(loc.id),
            )
        )
        session.commit()

        out = enrich_merged_locations_for_review(
            session,
            project_id=int(project.id),
            run_id="run-2",
            article_id=int(article.id),
            merged_locations=[
                {
                    "anchor": "p1",
                    "location": {"id": "p1"},
                }
            ],
        )
        assert out[0]["persisted_location_id"] == int(loc.id)
        assert "stylebook_link" not in out[0]
