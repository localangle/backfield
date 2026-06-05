"""Unit tests for processed-item review enrichment."""

from __future__ import annotations

from api.processed_item.entities.location.review_enrichment import (
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
    SubstrateLocationMentionOccurrence,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
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


def test_enrich_appends_manual_location_without_model_row() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Manual Org", slug="manual-org")
        session.add(org)
        session.commit()
        session.refresh(org)

        project = BackfieldProject(
            organization_id=int(org.id),
            name="Manual Proj",
            slug="manual-proj",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        article = SubstrateArticle(
            project_id=int(project.id),
            headline="Manual",
            text="Neighbors gathered at Lincoln School after the storm.",
        )
        session.add(article)
        session.commit()
        session.refresh(article)

        loc = SubstrateLocation(
            project_id=int(project.id),
            name="Lincoln School",
            normalized_name="lincoln school",
            location_type="place",
            status="active",
            source_kind="manual_add",
            source_details_json={
                "source": "agate_review_add_place",
                "run_id": "run-manual",
                "raw_entry_id": "user_place:123",
            },
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        mention = SubstrateLocationMention(
            article_id=int(article.id),
            location_id=int(loc.id),
            role_in_story="Shelter",
            added=True,
            source_kind="manual_add",
        )
        session.add(mention)
        session.commit()
        session.refresh(mention)
        session.add(
            SubstrateLocationMentionOccurrence(
                location_mention_id=int(mention.id),
                mention_text="Lincoln School",
                quote_text="Lincoln School after the storm.",
                start_char=22,
                end_char=53,
                occurrence_order=0,
                source_kind="manual_add",
            )
        )
        session.commit()

        out = enrich_merged_locations_for_review(
            session,
            project_id=int(project.id),
            run_id="run-manual",
            article_id=int(article.id),
            merged_locations=[],
        )
        assert len(out) == 1
        row = out[0]
        assert row["anchor"] == "user_place:123"
        assert row["source"] == "user"
        assert row["persisted_location_id"] == int(loc.id)
        assert row["location"]["location"]["full"] == "Lincoln School"
        assert row["location"]["type"] == "place"
        assert row["location"]["role_in_story"] == "Shelter"
        assert row["mention_occurrences"][0]["mention_text"] == "Lincoln School"
        assert row["mention_occurrences"][0]["quote_text"] == "Lincoln School after the storm."


def test_enrich_matches_h3_rows_by_display_name_suffix() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Org H3", slug="org-h3")
        session.add(org)
        session.commit()
        session.refresh(org)

        project = BackfieldProject(
            organization_id=int(org.id),
            name="Proj H3",
            slug="proj-h3",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        article = SubstrateArticle(project_id=int(project.id), headline="H", text="B")
        session.add(article)
        session.commit()
        session.refresh(article)

        locs: list[SubstrateLocation] = []
        for raw_entry_id, name in (
            ("h3:abc:carson's, lincolnwood town center", "Carson's, Lincolnwood Town Center"),
            ("h3:abc:kohl's, lincolnwood town center", "Kohl's, Lincolnwood Town Center"),
        ):
            loc = SubstrateLocation(
                project_id=int(project.id),
                name=name,
                normalized_name=name.lower(),
                canonical_link_status=CANONICAL_LINK_PENDING,
                source_details_json={"run_id": "run-h3", "raw_entry_id": raw_entry_id},
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
            locs.append(loc)
        session.commit()

        out = enrich_merged_locations_for_review(
            session,
            project_id=int(project.id),
            run_id="run-h3",
            article_id=int(article.id),
            merged_locations=[
                {
                    "anchor": "stylebook_output:0",
                    "location": {
                        "id": "h3:abc",
                        "location": "Carson's, Lincolnwood Town Center",
                    },
                },
                {
                    "anchor": "stylebook_output:1",
                    "location": {
                        "id": "h3:abc",
                        "location": "Kohl's, Lincolnwood Town Center",
                    },
                },
            ],
        )
        assert out[0]["persisted_location_id"] == int(locs[0].id)
        assert out[1]["persisted_location_id"] == int(locs[1].id)


def test_enrich_omits_stylebook_link_when_mention_deleted_for_article() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Org3", slug="org-enrich-3")
        session.add(org)
        session.commit()
        session.refresh(org)

        stylebook = Stylebook(
            organization_id=int(org.id),
            name="SB3",
            slug="sb-enrich-3",
            is_default=True,
        )
        session.add(stylebook)
        session.commit()
        session.refresh(stylebook)

        project = BackfieldProject(
            organization_id=int(org.id),
            name="Proj3",
            slug="proj-enrich-3",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        article = SubstrateArticle(project_id=int(project.id), headline="H", text="B")
        session.add(article)
        session.commit()
        session.refresh(article)

        canon = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),
            label="South Shore",
            slug="south-shore",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
            geometry_type="Point",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        loc = SubstrateLocation(
            project_id=int(project.id),
            name="South Shore",
            normalized_name="south shore",
            stylebook_location_canonical_id=str(canon.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
            source_details_json={"run_id": "run-3", "raw_entry_id": "ss1"},
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        session.add(
            SubstrateLocationMention(
                article_id=int(article.id),
                location_id=int(loc.id),
                deleted=True,
            )
        )
        session.commit()

        out = enrich_merged_locations_for_review(
            session,
            project_id=int(project.id),
            run_id="run-3",
            article_id=int(article.id),
            merged_locations=[
                {
                    "anchor": "ss1",
                    "location": {"id": "ss1", "description": "South Shore"},
                }
            ],
        )
        assert "stylebook_link" not in out[0]
        assert "persisted_location_id" not in out[0]
