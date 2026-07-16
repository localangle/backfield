from __future__ import annotations

import pytest
from backfield_db import (
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.entities.location.persist import assert_canonical_link_invariant
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate import _find_mention_span, persist_from_consolidated
from worker.substrate.content.article import _upsert_article
from worker.substrate.content.geography_reset import replace_machine_geography_for_article

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
WGP_POINT = {"type": "Point", "coordinates": [-87.703, 41.914]}


def test_find_mention_span_strips_trailing_punctuation_not_in_article() -> None:
    haystack = (
        "Violet Harris, a 15-year-old student, was killed after a vehicle crashed into "
        "the electric scooter she was riding last month in South Shore"
    )
    needle = haystack + "."
    assert haystack.find(needle) < 0
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span is not None
    start, end = span
    assert haystack[start:end] == haystack
    assert end == len(haystack)


def test_find_mention_span_exact_match_still_preferred() -> None:
    haystack = "We met in South Shore."
    assert _find_mention_span(haystack=haystack, needle="South Shore.") == (10, 22)


def test_find_mention_span_unifies_curly_and_straight_quotes() -> None:
    haystack = 'He was "still processing" the news.'
    needle = "He was 'still processing' the news."
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span == (0, len(haystack))


def test_find_mention_span_falls_back_when_paraphrase_differs() -> None:
    haystack = (
        'Ald. Desmon Yancy (5th) said Thursday morning he was "still processing" '
        "the shooting in his ward."
    )
    needle = (
        "Fifth Ward Ald. Desmon Yancy said Thursday morning he was 'still processing' "
        "the shooting in his ward."
    )
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span is not None
    start, end = span
    excerpt = haystack[start:end]
    assert len(excerpt) >= 12
    assert excerpt in haystack
    assert "still processing" in excerpt or "Desmon Yancy" in excerpt


def test_review_rejection_does_not_persist_geocode_identity_or_cache() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-review-geocode",
            project_slug="proj-review-geocode",
        )
        session.add(AgateRun(id="run-review-geocode", graph_id="graph-review", status="pending"))
        session.commit()
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-review",
            run_id="run-review-geocode",
            consolidated={
                "text": "The event used 1400 Example Avenue.",
                "url": "https://example.com/review-geocode",
                "places": {
                    "areas": {
                        "states": [],
                        "counties": [],
                        "cities": [],
                        "neighborhoods": [],
                        "regions": [],
                        "other": [],
                    },
                    "points": [],
                    "needs_review": [
                        {
                            "id": "provider:wrong",
                            "location": "1400 Example Avenue, Metro, IL",
                            "type": "address",
                            "original_text": "1400 Example Avenue",
                            "geocode_qa_code": "geocode_subnational_mismatch",
                            "geocode": {
                                "geocode_type": "test",
                                "result": {
                                    "id": "provider:wrong",
                                    "formatted_address": "1400 Example Avenue, Elsewhere, CA",
                                    "geometry": {
                                        "type": "Point",
                                        "coordinates": [-118.0, 34.0],
                                    },
                                },
                            },
                            "mentions": [{"text": "1400 Example Avenue"}],
                        }
                    ],
                },
            },
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

        location = session.exec(select(SubstrateLocation)).one()
        assert location.status == "needs_review"
        assert location.external_source is None
        assert location.external_id is None
        assert location.formatted_address is None
        assert location.geometry_json is None
        assert location.h3_cell is None
        assert session.exec(select(SubstrateLocationCache)).all() == []


def _bootstrap_project(session: Session, *, org_slug: str, project_slug: str) -> int:
    org = BackfieldOrganization(name="Org", slug=org_slug)
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid,
        stylebook_id=sb_id,
        name="Workspace",
        slug="ws",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    proj = BackfieldProject(
        organization_id=oid,
        name="Proj",
        slug=project_slug,
        workspace_id=int(ws.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)

    return int(proj.id)  # type: ignore[arg-type]


def _city_places(
    *,
    entry_id: str = "city:1",
    geocode_id: str = "pelias:chicago",
    name: str = "Chicago, IL",
    formatted_address: str = "Chicago, IL, USA",
    geometry: dict = CHICAGO_POINT,
) -> dict:
    return {
        "areas": {
            "states": [],
            "counties": [],
            "cities": [
                {
                    "id": entry_id,
                    "original_text": "Chicago",
                    "description": "Mentioned as the setting for the story.",
                    "role_in_story": "Setting",
                    "nature": "primary",
                    "nature_secondary_tags": ["context"],
                    "location": name,
                    "type": "city",
                    "geocode": {
                        "geocode_type": "pelias",
                        "result": {
                            "id": geocode_id,
                            "formatted_address": formatted_address,
                            "geometry": geometry,
                        },
                    },
                }
            ],
            "neighborhoods": [],
            "regions": [],
            "other": [],
        },
        "points": [],
        "needs_review": [],
    }


def _empty_places() -> dict:
    return {
        "areas": {
            "states": [],
            "counties": [],
            "cities": [],
            "neighborhoods": [],
            "regions": [],
            "other": [],
        },
        "points": [],
        "needs_review": [],
    }


def test_upsert_article_reuses_existing_row_by_publication_and_entry_id() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    article_url = (
        "https://chicago.suntimes.com/letters-to-the-editor/2026/06/05/"
        "bears-stadium-joe-sedelmaier-commercials-teen-takeovers-safety"
    )

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-art", project_slug="proj-art")
        session.add(AgateRun(id="run-a1", graph_id="graph-a1", status="pending"))
        session.add(
            SubstrateArticle(
                project_id=project_id,
                external_source="Chicago Sun-Times",
                external_id=article_url,
                url=article_url,
                headline="Original headline",
                text="Original body",
                source_run_id="run-a1",
            )
        )
        session.commit()

        consolidated = {
            "url": article_url,
            "publication": "Chicago Sun-Times",
            "entry_id": article_url,
            "headline": "Updated headline",
            "text": "Updated body",
            "author": "Letters to the Editor",
            "pub_date": "2026-06-05",
        }
        article = _upsert_article(
            session,
            project_id=project_id,
            consolidated=consolidated,
            run_id="run-a2",
        )
        article_id = int(article.id)  # type: ignore[arg-type]
        session.commit()

    with Session(engine) as session:
        rows = list(session.exec(select(SubstrateArticle)).all())
        assert len(rows) == 1
        row = rows[0]
        assert int(row.id) == article_id
        assert row.headline == "Updated headline"
        assert row.text == "Updated body"
        assert row.source_run_id == "run-a2"


def test_persist_graph_outputs_writes_article_location_mention_occurrence() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org", project_slug="proj")
        session.add(AgateRun(id="run-1", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "description": "Mentioned as the setting for the story.",
                            "role_in_story": "Setting",
                            "nature": "primary",
                            "nature_secondary_tags": ["context"],
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-1",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import (
            SubstrateArticle,
            SubstrateLocation,
            SubstrateLocationMention,
            SubstrateLocationMentionOccurrence,
        )

        articles = session.exec(select(SubstrateArticle)).all()
        assert len(articles) == 1
        assert articles[0].text == "Hello Chicago."
        assert articles[0].source_run_id == "run-1"

        locations = session.exec(select(SubstrateLocation)).all()
        assert len(locations) == 1
        assert locations[0].external_source == "pelias"

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 1
        assert canon_rows[0].primary_substrate_location_id is None
        assert locations[0].stylebook_location_canonical_id is not None
        assert locations[0].stylebook_location_canonical_id == canon_rows[0].id
        assert locations[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert_canonical_link_invariant(locations[0])
        alias_rows = session.exec(select(StylebookLocationAlias)).all()
        norms = {str(a.normalized_alias) for a in alias_rows}
        assert "chicago, il" in norms
        assert "chicago il" in norms
        assert locations[0].normalized_name in norms

        mentions = session.exec(select(SubstrateLocationMention)).all()
        assert len(mentions) == 1
        assert mentions[0].role_in_story == "Setting"
        assert mentions[0].nature == "primary"
        assert mentions[0].nature_secondary_tags_json == ["context"]

        occ = session.exec(select(SubstrateLocationMentionOccurrence)).all()
        assert len(occ) == 1
        assert occ[0].mention_text == "Chicago"
        assert occ[0].suppressed is False
        assert occ[0].start_char == 6
        assert occ[0].end_char == 13
        assert occ[0].occurrence_order == 0


def test_add_only_skips_existing_match_without_updating_or_removing() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-add", project_slug="proj-add")
        session.add(AgateRun(id="run-add-1", graph_id="graph-add", status="pending"))
        session.add(AgateRun(id="run-add-2", graph_id="graph-add", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-add",
            run_id="run-add-1",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/add",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        first = session.exec(select(SubstrateLocation)).one()
        first_updated_at = first.updated_at

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-add",
            run_id="run-add-2",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/add",
                "places": _city_places(formatted_address="Changed address"),
            },
            db_output_params={"reconciliation_policy": "add_only"},
        )
        session.commit()

        loc = session.get(SubstrateLocation, int(first.id))
        assert loc is not None
        assert loc.formatted_address == "Chicago, IL, USA"
        assert loc.updated_at == first_updated_at
        assert result.reconciliation_summary.skipped == 1
        assert result.reconciliation_summary.updated == 0


def test_h3_point_ids_do_not_collapse_distinct_pois() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    shared_h3 = "h3:8c2664d837691ff"
    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-h3", project_slug="proj-h3")
        session.add(AgateRun(id="run-h3", graph_id="graph-h3", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-h3",
            run_id="run-h3",
            consolidated={
                "text": "Buying a new suit at Carsons. Buying polos at Kohl's.",
                "places": {
                    "areas": {
                        "states": [],
                        "counties": [],
                        "cities": [],
                        "neighborhoods": [],
                        "regions": [],
                        "other": [],
                    },
                    "points": [
                        {
                            "id": shared_h3,
                            "original_text": "Buying a new suit at Carsons.",
                            "location": "Carson's, Lincolnwood Town Center",
                            "type": "place",
                            "geocode": {
                                "geocode_type": "h3",
                                "result": {
                                    "id": shared_h3,
                                    "formatted_address": "Lincolnwood Town Center",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        },
                        {
                            "id": shared_h3,
                            "original_text": "Buying polos at Kohl's.",
                            "location": "Kohl's, Lincolnwood Town Center",
                            "type": "place",
                            "geocode": {
                                "geocode_type": "h3",
                                "result": {
                                    "id": shared_h3,
                                    "formatted_address": "Lincolnwood Town Center",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        },
                    ],
                    "needs_review": [],
                },
            },
        )
        session.commit()

        locations = session.exec(select(SubstrateLocation)).all()
        assert len(locations) == 2
        assert {loc.name for loc in locations} == {
            "Carson's, Lincolnwood Town Center",
            "Kohl's, Lincolnwood Town Center",
        }
        assert {loc.external_source for loc in locations} == {None}
        raw_ids = {
            loc.source_details_json["raw_entry_id"]
            for loc in locations
            if isinstance(loc.source_details_json, dict)
        }
        assert raw_ids == {
            "h3:8c2664d837691ff:carson's, lincolnwood town center",
            "h3:8c2664d837691ff:kohl's, lincolnwood town center",
        }
        for loc in locations:
            assert loc.h3_cell
            assert loc.h3_resolution == 11


def test_shared_geocoder_address_id_does_not_collapse_distinct_pois() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    shared_geocoder_id = "openaddresses:address:us/il/cook:96ada5d99403297d"
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-shared-geocoder",
            project_slug="proj-shared-geocoder",
        )
        session.add(
            AgateRun(id="run-shared-geocoder", graph_id="graph-shared-geocoder", status="pending")
        )
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-shared-geocoder",
            run_id="run-shared-geocoder",
            consolidated={
                "text": "Buying a new suit at Carsons. Buying polos at Kohl's.",
                "places": {
                    "areas": {
                        "states": [],
                        "counties": [],
                        "cities": [],
                        "neighborhoods": [],
                        "regions": [],
                        "other": [],
                    },
                    "points": [
                        {
                            "id": "h3:shared-cell",
                            "original_text": "Buying a new suit at Carsons.",
                            "location": "Carson's, Lincolnwood Town Center, Lincolnwood, IL",
                            "type": "place",
                            "geocode": {
                                "geocode_type": "pelias_structured",
                                "result": {
                                    "id": shared_geocoder_id,
                                    "formatted_address": "3333 West Touhy Avenue, Lincolnwood, IL",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        },
                        {
                            "id": "h3:shared-cell",
                            "original_text": "Buying polos at Kohl's.",
                            "location": "Kohl's, Lincolnwood Town Center, Lincolnwood, IL",
                            "type": "place",
                            "geocode": {
                                "geocode_type": "pelias_structured",
                                "result": {
                                    "id": shared_geocoder_id,
                                    "formatted_address": "3333 West Touhy Avenue, Lincolnwood, IL",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        },
                    ],
                    "needs_review": [],
                },
            },
        )
        session.commit()

        locations = session.exec(select(SubstrateLocation)).all()
        assert len(locations) == 2
        assert {loc.name for loc in locations} == {
            "Carson's, Lincolnwood Town Center, Lincolnwood, IL",
            "Kohl's, Lincolnwood Town Center, Lincolnwood, IL",
        }
        assert {loc.external_source for loc in locations} == {"geocoder"}
        assert {loc.external_id for loc in locations} == {
            f"{shared_geocoder_id}:carson-s-lincolnwood-town-center-lincolnwood-il",
            f"{shared_geocoder_id}:kohl-s-lincolnwood-town-center-lincolnwood-il",
        }
        active_mentions = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False)
            )
        ).all()
        assert len(active_mentions) == 2


def test_add_only_does_not_remove_stale_saved_places() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-add-stale", project_slug="proj-add-stale"
        )
        session.add(
            AgateRun(id="run-add-stale-1", graph_id="graph-add-stale", status="pending")
        )
        session.add(
            AgateRun(id="run-add-stale-2", graph_id="graph-add-stale", status="pending")
        )
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-add-stale",
            run_id="run-add-stale-1",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/add-stale",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-add-stale",
            run_id="run-add-stale-2",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/add-stale",
                "places": _empty_places(),
            },
            db_output_params={"reconciliation_policy": "add_only"},
        )
        session.commit()

        active = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False)
            )
        ).all()
        assert len(active) == 1
        assert result.reconciliation_summary.removed == 0


def test_smart_merge_preserves_editor_touched_stale_places() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-smart-preserve",
            project_slug="proj-smart-preserve",
        )
        session.add(
            AgateRun(
                id="run-smart-preserve-1",
                graph_id="graph-smart-preserve",
                status="pending",
            )
        )
        session.add(
            AgateRun(
                id="run-smart-preserve-2",
                graph_id="graph-smart-preserve",
                status="pending",
            )
        )
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-smart-preserve",
            run_id="run-smart-preserve-1",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/smart-preserve",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        mention = session.exec(select(SubstrateLocationMention)).one()
        mention.edited = True
        session.add(mention)
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-smart-preserve",
            run_id="run-smart-preserve-2",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/smart-preserve",
                "places": _empty_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        active = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False)
            )
        ).all()
        assert len(active) == 1
        assert active[0].edited is True
        assert result.reconciliation_summary.removed == 0


def test_replace_clears_editor_touched_places_and_allows_future_readd() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-replace", project_slug="proj-replace"
        )
        session.add(AgateRun(id="run-replace-1", graph_id="graph-replace", status="pending"))
        session.add(AgateRun(id="run-replace-2", graph_id="graph-replace", status="pending"))
        session.add(AgateRun(id="run-replace-3", graph_id="graph-replace", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-replace",
            run_id="run-replace-1",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/replace",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        mention = session.exec(select(SubstrateLocationMention)).one()
        mention.edited = True
        session.add(mention)
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-replace",
            run_id="run-replace-2",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/replace",
                "places": _empty_places(),
            },
            db_output_params={"reconciliation_policy": "replace"},
        )
        session.commit()

        assert result.reconciliation_summary.removed == 1
        active = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False)
            )
        ).all()
        assert active == []
        assert session.exec(select(SubstrateLocation)).all() == []

        readd = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-replace",
            run_id="run-replace-3",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/replace",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()
        assert readd.reconciliation_summary.added == 1
        assert len(session.exec(select(SubstrateLocationMention)).all()) == 1


def test_reconciliation_failure_rolls_back_prior_saved_places(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-atomic", project_slug="proj-atomic")
        session.add(AgateRun(id="run-atomic-1", graph_id="graph-atomic", status="pending"))
        session.add(AgateRun(id="run-atomic-2", graph_id="graph-atomic", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-atomic",
            run_id="run-atomic-1",
            consolidated={
                "text": "Hello Chicago.",
                "url": "https://e.test/atomic",
                "places": _city_places(),
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        original_mention = session.exec(select(SubstrateLocationMention)).one()
        original_location = session.exec(select(SubstrateLocation)).one()
        original_mention_id = int(original_mention.id)
        original_location_id = int(original_location.id)

        def fail_mention(*_args, **_kwargs) -> None:
            raise RuntimeError("simulated mention failure")

        monkeypatch.setattr(
            "worker.substrate.entities.location.handler._upsert_mention_and_occurrence",
            fail_mention,
        )

        with pytest.raises(RuntimeError, match="simulated mention failure"):
            persist_from_consolidated(
                session,
                project_id=project_id,
                graph_id="graph-atomic",
                run_id="run-atomic-2",
                consolidated={
                    "text": "Hello Chicago.",
                    "url": "https://e.test/atomic",
                    "places": _city_places(geocode_id="pelias:atomic-new"),
                },
                db_output_params={"reconciliation_policy": "replace"},
            )
        session.rollback()

        mention = session.get(SubstrateLocationMention, original_mention_id)
        location = session.get(SubstrateLocation, original_location_id)
        assert mention is not None
        assert mention.deleted is False
        assert location is not None
        assert location.external_id == "pelias:chicago"
        active_mentions = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False)
            )
        ).all()
        assert len(active_mentions) == 1


def test_persist_geocodio_id_sets_external_source() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org_gc", project_slug="proj_gc")
        session.add(AgateRun(id="run-gc", graph_id="graph-gc", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello El Campo.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:gc1",
                            "original_text": "El Campo",
                            "description": "Setting.",
                            "role_in_story": "Setting",
                            "nature": "primary",
                            "nature_secondary_tags": [],
                            "location": "El Campo, TX",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "geocodio_structured",
                                "result": {
                                    "id": "geocodio:gcod_fixture_key",
                                    "formatted_address": "El Campo, TX 77437, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-gc",
            run_id="run-gc",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateArticle, SubstrateLocation

        articles = session.exec(select(SubstrateArticle)).all()
        assert len(articles) == 1

        locations = session.exec(select(SubstrateLocation)).all()
        assert len(locations) == 1
        assert locations[0].external_source == "geocodio"
        assert locations[0].external_id == "geocodio:gcod_fixture_key"


def test_persist_stylebook_canonical_id_prefixes_external_id() -> None:
    sb_uuid = "550e8400-e29b-41d4-a716-446655440000"
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org_sb", project_slug="proj_sb")
        session.add(AgateRun(id="run-sb", graph_id="graph-sb", status="pending"))
        session.commit()

        consolidated = {
            "text": "Cached place.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:sb1",
                            "original_text": "Example City",
                            "location": "Example City, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "canonical_db",
                                "result": {
                                    "id": "pelias:ignored_when_canonical_present",
                                    "canonical_id": sb_uuid,
                                    "formatted_address": "Example City, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-sb",
            run_id="run-sb",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].external_source == "stylebook_location"
        assert locs[0].external_id == f"stylebook:{sb_uuid}:example-city-il"


def test_persist_stylebook_id_keeps_full_prefixed_external_id() -> None:
    sb_uuid = "660e8400-e29b-41d4-a716-446655440001"
    prefixed = f"stylebook:{sb_uuid}:other-city-wi"
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org_sb2", project_slug="proj_sb2")
        session.add(AgateRun(id="run-sb2", graph_id="graph-sb2", status="pending"))
        session.commit()

        consolidated = {
            "text": "Stylebook id only.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:sb2",
                            "original_text": "Other City",
                            "location": "Other City, WI",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "canonical_db",
                                "result": {
                                    "id": f"stylebook:{sb_uuid}",
                                    "formatted_address": "Other City, WI, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-sb2",
            run_id="run-sb2",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].external_source == "stylebook_location"
        assert locs[0].external_id == prefixed


def test_persist_stylebook_canonical_id_no_double_prefix() -> None:
    sb_uuid = "770e8400-e29b-41d4-a716-446655440002"
    already = f"stylebook:{sb_uuid}:third-city-mn"
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org_sb3", project_slug="proj_sb3")
        session.add(AgateRun(id="run-sb3", graph_id="graph-sb3", status="pending"))
        session.commit()

        consolidated = {
            "text": "Prefixed canonical.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:sb3",
                            "original_text": "Third City",
                            "location": "Third City, MN",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "canonical_db",
                                "result": {
                                    "id": "pelias:x",
                                    "canonical_id": f"stylebook:{sb_uuid}",
                                    "formatted_address": "Third City, MN, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-sb3",
            run_id="run-sb3",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].external_source == "stylebook_location"
        assert locs[0].external_id == already


def test_persist_stylebook_canonical_splits_fine_grained_poi_by_display_name() -> None:
    sb_uuid = "cdf548d6-7c91-461f-ba70-7897e0092985"
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _canonical_point(*, place_id: str, original_text: str) -> dict:
        return {
            "id": place_id,
            "original_text": original_text,
            "location": original_text,
            "type": "point",
            "geocode": {
                "geocode_type": "canonical_db",
                "result": {
                    "id": f"stylebook:{sb_uuid}",
                    "canonical_id": sb_uuid,
                    "formatted_address": "Orland Park, IL, USA",
                    "geometry": WGP_POINT,
                },
            },
        }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org_poi", project_slug="proj_poi")
        session.add(AgateRun(id="run-poi", graph_id="graph-poi", status="pending"))
        session.commit()

        consolidated = {
            "text": "Shoppers visited Carson's and Kohl's at the mall.",
            "url": "https://example.com/mall-shoppers",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    _canonical_point(place_id="poi:carsons", original_text="Carson's"),
                    _canonical_point(place_id="poi:kohls", original_text="Kohl's"),
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-poi",
            run_id="run-poi",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 2
        external_ids = {loc.external_id for loc in locs}
        assert external_ids == {
            f"stylebook:{sb_uuid}:carson-s",
            f"stylebook:{sb_uuid}:kohl-s",
        }

        mentions = session.exec(select(SubstrateLocationMention)).all()
        assert len(mentions) == 2


def test_persist_stylebook_canonical_collapses_same_poi_display_name() -> None:
    sb_uuid = "8f3b2c4a-1e2d-4f5a-9b8c-7d6e5f4a3b2c"
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _canonical_point(*, place_id: str) -> dict:
        return {
            "id": place_id,
            "original_text": "Carson's",
            "location": "Carson's",
            "type": "point",
            "geocode": {
                "geocode_type": "canonical_db",
                "result": {
                    "canonical_id": sb_uuid,
                    "formatted_address": "Orland Park, IL, USA",
                    "geometry": WGP_POINT,
                },
            },
        }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org_poi_dup", project_slug="proj_poi_dup"
        )
        session.add(AgateRun(id="run-poi-dup", graph_id="graph-poi-dup", status="pending"))
        session.commit()

        consolidated = {
            "text": "Carson's appeared twice in the story.",
            "url": "https://example.com/carsons-twice",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    _canonical_point(place_id="poi:carsons-a"),
                    _canonical_point(place_id="poi:carsons-b"),
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-poi-dup",
            run_id="run-poi-dup",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].external_id == f"stylebook:{sb_uuid}:carson-s"
        mentions = session.exec(select(SubstrateLocationMention)).all()
        assert len(mentions) == 1


def test_persist_graph_outputs_suppresses_prior_occurrences_on_repeat() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org2", project_slug="proj2")
        session.add(AgateRun(id="run-1", graph_id="graph-1", status="pending"))
        session.add(AgateRun(id="run-2", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-1",
            consolidated=consolidated,
        )
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-2",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocationMentionOccurrence

        occ = session.exec(
            select(SubstrateLocationMentionOccurrence).order_by(
                col(SubstrateLocationMentionOccurrence.id)
            )
        ).all()
        assert len(occ) == 2
        assert sum(1 for row in occ if row.suppressed) == 1
        assert sum(1 for row in occ if not row.suppressed) == 1


def test_rerun_retires_stale_article_mentions_when_geocode_identity_changes() -> None:
    """Re-run with new geocode ids must not leave duplicate active mentions on the article."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-rerun", project_slug="proj-rerun")
        session.add(AgateRun(id="run-a", graph_id="graph-r", status="pending"))
        session.add(AgateRun(id="run-b", graph_id="graph-r", status="pending"))
        session.commit()

        run1_places = {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [],
                "neighborhoods": [],
                "regions": [],
                "other": [],
            },
            "points": [
                {
                    "id": "franklin",
                    "original_text": "500 N Franklin",
                    "location": "500 N Franklin St, Chicago, IL",
                    "type": "address",
                    "geocode": {
                        "geocode_type": "pelias",
                        "result": {
                            "id": "pelias:franklin",
                            "formatted_address": "500 N Franklin, Chicago, IL",
                            "geometry": CHICAGO_POINT,
                        },
                    },
                },
                {
                    "id": "midway",
                    "original_text": "Midway Airport",
                    "location": "Midway Airport, Chicago, IL",
                    "type": "place",
                    "geocode": {
                        "geocode_type": "pelias",
                        "result": {
                            "id": "pelias:midway-old",
                            "formatted_address": "5700 S Cicero Ave, Chicago, IL",
                            "geometry": CHICAGO_POINT,
                        },
                    },
                },
            ],
            "needs_review": [],
        }
        run2_places = {
            **run1_places,
            "points": [
                run1_places["points"][0],
                {
                    "id": "midway",
                    "original_text": "Midway Airport",
                    "location": "Midway Airport, Chicago, IL",
                    "type": "place",
                    "geocode": {
                        "geocode_type": "pelias",
                        "result": {
                            "id": "pelias:midway-new",
                            "formatted_address": "5700 South Cicero Avenue, Chicago, IL",
                            "geometry": CHICAGO_POINT,
                        },
                    },
                },
            ],
        }
        text = "Story at 500 N Franklin in Chicago."
        _, retired0, disposed0, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-r",
            run_id="run-a",
            consolidated={"text": text, "places": run1_places},
        )
        assert retired0 == 0
        assert disposed0 == 0
        _, retired1, disposed1, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-r",
            run_id="run-b",
            consolidated={"text": text, "places": run2_places},
        )
        assert retired1 == 1
        assert disposed1 == 1
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation, SubstrateLocationMention

        active = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False),
            )
        ).all()
        assert len(active) == 2
        retired = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(True),
            )
        ).all()
        assert len(retired) == 1
        old_loc_ids = {int(m.location_id) for m in retired}
        old_locs = session.exec(
            select(SubstrateLocation).where(col(SubstrateLocation.id).in_(list(old_loc_ids)))
        ).all()
        assert len(old_locs) == 0
        midway_new = session.exec(
            select(SubstrateLocation).where(
                SubstrateLocation.external_id == "pelias:midway-new"
            )
        ).one()
        assert midway_new.external_id == "pelias:midway-new"


def test_superseded_ingest_disposes_linked_substrate_with_no_remaining_mentions() -> None:
    """Mirrors batch re-feed: new geocode identity retires mention and removes orphan linked row."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    region_places = {
        "areas": {
            "states": [],
            "counties": [],
            "cities": [],
            "neighborhoods": [],
            "regions": [
                {
                    "id": "region:redline",
                    "original_text": "At the other end of the Red Line",
                    "description": "Transit line reference",
                    "location": "Red Line, Chicago, IL",
                    "type": "region_city",
                    "geocode": {
                        "geocode_type": "region_llm",
                        "result": {
                            "id": "region:redline-old",
                            "processed_str": "Red Line, Chicago, IL (region estimate)",
                            "geometry": CHICAGO_POINT,
                        },
                    },
                }
            ],
            "other": [],
        },
        "points": [],
        "needs_review": [],
    }
    cache_places = {
        **region_places,
        "areas": {
            **region_places["areas"],
            "regions": [
                {
                    **region_places["areas"]["regions"][0],
                    "geocode": {
                        "geocode_type": "stylebook",
                        "result": {
                            "id": "stylebook:placeholder",
                            "formatted_address": "Red Line, Chicago, IL",
                            "geometry": CHICAGO_POINT,
                        },
                    },
                }
            ],
        },
    }

    with Session(engine) as session:
        from backfield_entities.canonical.link import CANONICAL_LINK_LINKED

        project_id = _bootstrap_project(session, org_slug="org-red", project_slug="proj-red")
        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)

        session.add(AgateRun(id="run-red-a", graph_id="graph-red", status="pending"))
        session.add(AgateRun(id="run-red-b", graph_id="graph-red", status="pending"))
        session.commit()

        url = "https://example.com/white-sox-red-line"
        text = "At the other end of the Red Line, fans hoped for a meaningful summer."
        _, retired0, disposed0, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-red",
            run_id="run-red-a",
            consolidated={"text": text, "url": url, "places": region_places},
            db_output_params={"auto_apply_canonicalization": True, "stylebook_id": sb_id},
        )
        assert retired0 == 0
        assert disposed0 == 0
        session.commit()

        old_loc = session.exec(
            select(SubstrateLocation).where(SubstrateLocation.external_id == "region:redline-old")
        ).one()
        old_lid = int(old_loc.id)
        cid = str(old_loc.stylebook_location_canonical_id)
        assert cid
        assert old_loc.canonical_link_status == CANONICAL_LINK_LINKED

        cache_places["areas"]["regions"][0]["geocode"]["result"]["id"] = f"stylebook:{cid}"
        _, retired1, disposed1, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-red",
            run_id="run-red-b",
            consolidated={"text": text, "url": url, "places": cache_places},
            db_output_params={"auto_apply_canonicalization": True, "stylebook_id": sb_id},
        )
        assert retired1 == 1
        assert disposed1 == 1
        session.commit()

    with Session(engine) as session:
        assert session.get(SubstrateLocation, old_lid) is None
        active = session.exec(
            select(SubstrateLocationMention).where(
                col(SubstrateLocationMention.deleted).is_(False),
            )
        ).all()
        assert len(active) == 1
        linked = session.exec(
            select(SubstrateLocation).where(
                SubstrateLocation.stylebook_location_canonical_id == cid
            )
        ).all()
        assert len(linked) == 1
        assert linked[0].external_id == f"stylebook:{cid}:red-line-chicago-il"


def test_superseded_ingest_keeps_substrate_when_other_stories_still_mention() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    places_v1 = {
        "areas": {
            "states": [],
            "counties": [],
            "cities": [],
            "neighborhoods": [],
            "regions": [],
            "other": [],
        },
        "points": [
            {
                "id": "shared",
                "original_text": "Midway Airport",
                "location": "Midway Airport, Chicago, IL",
                "type": "place",
                "geocode": {
                    "geocode_type": "pelias",
                    "result": {
                        "id": "pelias:shared-old",
                        "formatted_address": "5700 S Cicero Ave, Chicago, IL",
                        "geometry": CHICAGO_POINT,
                    },
                },
            }
        ],
        "needs_review": [],
    }
    places_v2 = {
        **places_v1,
        "points": [
            {
                **places_v1["points"][0],
                "geocode": {
                    "geocode_type": "pelias",
                    "result": {
                        "id": "pelias:shared-new",
                        "formatted_address": "5700 South Cicero Avenue, Chicago, IL",
                        "geometry": CHICAGO_POINT,
                    },
                },
            }
        ],
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-keep", project_slug="proj-keep")
        session.add(AgateRun(id="run-ka", graph_id="graph-k", status="pending"))
        session.add(AgateRun(id="run-kb", graph_id="graph-k", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-k",
            run_id="run-ka",
            consolidated={
                "text": "Story A at Midway.",
                "url": "https://example.com/story-a",
                "places": places_v1,
            },
        )
        session.commit()

        old_loc = session.exec(
            select(SubstrateLocation).where(SubstrateLocation.external_id == "pelias:shared-old")
        ).one()
        old_lid = int(old_loc.id)

        art_b = SubstrateArticle(
            project_id=project_id,
            url="https://example.com/story-b",
            headline="Story B",
            text="Story B also cites Midway.",
            external_source="test",
            external_id="story-b",
        )
        session.add(art_b)
        session.commit()
        session.refresh(art_b)
        session.add(
            SubstrateLocationMention(
                article_id=int(art_b.id),
                location_id=old_lid,
                deleted=False,
                source_kind="agate_geocode",
            )
        )
        session.commit()

        _, retired, disposed, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-k",
            run_id="run-kb",
            consolidated={
                "text": "Story A at Midway again.",
                "url": "https://example.com/story-a",
                "places": places_v2,
            },
        )
        assert retired == 1
        assert disposed == 0
        session.commit()

    with Session(engine) as session:
        assert session.get(SubstrateLocation, old_lid) is not None
        remaining = session.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.location_id == old_lid,
                col(SubstrateLocationMention.deleted).is_(False),
            )
        ).all()
        assert len(remaining) == 1


def test_persist_writes_multiple_mentions_from_entry() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    body = "Ohio lawmakers advanced the bill. Later, Back in Ohio, the governor signed it."
    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-oh", project_slug="proj-oh")
        session.add(AgateRun(id="run-oh", graph_id="graph-oh", status="pending"))
        session.commit()

        consolidated = {
            "text": body,
            "places": {
                "areas": {
                    "states": [
                        {
                            "id": "state:oh",
                            "original_text": "Ohio lawmakers advanced the bill.",
                            "mentions": [
                                {"text": "Ohio lawmakers advanced the bill."},
                                {"text": "Back in Ohio, the governor signed it."},
                            ],
                            "location": "Ohio",
                            "type": "state",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:oh",
                                    "formatted_address": "Ohio, USA",
                                    "geometry": {"type": "Point", "coordinates": [-82.9, 40.4]},
                                },
                            },
                        }
                    ],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-oh",
            run_id="run-oh",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        occ = session.exec(
            select(SubstrateLocationMentionOccurrence).where(
                SubstrateLocationMentionOccurrence.suppressed == False  # noqa: E712
            )
        ).all()
        assert len(occ) == 2
        assert occ[0].occurrence_order == 0
        assert occ[1].occurrence_order == 1
        assert occ[0].start_char == body.find("Ohio")
        assert occ[1].start_char == body.find("Back in Ohio")


def test_persist_reingest_preserves_user_edit_occurrence() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-u", project_slug="proj-u")
        session.add(AgateRun(id="run-u1", graph_id="graph-u", status="pending"))
        session.add(AgateRun(id="run-u2", graph_id="graph-u", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "mentions": [{"text": "Chicago"}],
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-u",
            run_id="run-u1",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        mention = session.exec(select(SubstrateLocationMention)).first()
        assert mention is not None
        user_occ = SubstrateLocationMentionOccurrence(
            location_mention_id=int(mention.id),
            source_kind="user_edit",
            mention_text="User-added mention text",
            occurrence_order=99,
            suppressed=False,
        )
        session.add(user_occ)
        session.commit()

    with Session(engine) as session:
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-u",
            run_id="run-u2",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        occ = session.exec(select(SubstrateLocationMentionOccurrence)).all()
        active = [o for o in occ if not o.suppressed]
        assert any(o.source_kind == "user_edit" for o in active)
        system_active = [o for o in active if o.source_kind == "system_extraction"]
        assert len(system_active) == 1
        assert system_active[0].mention_text == "Chicago"


def test_find_mention_span_after_prior_match() -> None:
    body = "Ohio first. Then Ohio again."
    first = _find_mention_span(haystack=body, needle="Ohio")
    assert first == (0, 4)
    second = _find_mention_span(haystack=body, needle="Ohio", search_from=first[1] if first else 0)
    assert second == (17, 21)


def test_persist_defers_address_type_without_materializing_canonical() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-addr", project_slug="proj-addr")
        session.add(AgateRun(id="run-addr", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Ship to 123 Main St.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "addr:1",
                            "original_text": "123 Main St",
                            "location": "123 Main St, Chicago, IL",
                            "type": "address",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:addr",
                                    "formatted_address": "123 Main St, Chicago, IL",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-addr",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 0


def test_persist_links_preseeded_canonical_alias_without_second_canonical() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-link", project_slug="proj-link")
        session.add(AgateRun(id="run-link", graph_id="graph-1", status="pending"))
        session.commit()

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="seed",
                suppressed=False,
            )
        )
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "description": "Mentioned as the setting for the story.",
                            "role_in_story": "Setting",
                            "nature": "primary",
                            "nature_secondary_tags": ["context"],
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:other",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-link",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 1
        assert canon_rows[0].id == cid

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].stylebook_location_canonical_id == cid
        assert locs[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert_canonical_link_invariant(locs[0])


def test_persist_fuzzy_links_preseeded_canonical_when_alias_normalization_differs() -> None:
    """Exact ``normalized_alias`` misses; SQLite recall + difflib score should autolink."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-fuzzy", project_slug="proj-fuzzy")
        session.add(AgateRun(id="run-fuzzy", graph_id="graph-1", status="pending"))
        session.commit()

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="West Garfield Park, Chicago, IL",
            slug="west-garfield-park-chicago-il",
            location_type="neighborhood",
            primary_substrate_location_id=None,
            status="active",
            geometry_json=WGP_POINT,
            geometry_type="Point",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="West Garfield Park Chicago IL",
                normalized_alias="west garfield park chicago il",
                provenance="seed",
                suppressed=False,
            )
        )
        session.commit()

        consolidated = {
            "text": "News in West Garfield Park.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "nhood:1",
                            "original_text": "West Garfield Park",
                            "location": "West Garfield Park, Chicago, IL",
                            "type": "neighborhood",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:wgp",
                                    "formatted_address": "West Garfield Park, Chicago, IL, USA",
                                    "geometry": WGP_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-fuzzy",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 1
        assert canon_rows[0].id == cid

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].stylebook_location_canonical_id == cid
        assert locs[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert_canonical_link_invariant(locs[0])


def test_persist_materializes_canonical_for_city_without_geometry_when_no_match() -> None:
    """Non-excluded types auto-materialize when there is no link, even without geometry JSON."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-auto", project_slug="proj-auto")
        session.add(AgateRun(id="run-auto", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "News in Peoria.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:peoria",
                            "original_text": "Peoria",
                            "location": "Peoria, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:peoria",
                                    "formatted_address": "Peoria, IL, USA",
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-auto",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].geometry_json is None
        assert locs[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert locs[0].stylebook_location_canonical_id is not None

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 1
        fk = locs[0].stylebook_location_canonical_id
        canon = session.get(StylebookLocationCanonical, str(fk))
        assert canon is not None
        assert canon.location_type == "city"
        assert canon.formatted_address and "Peoria" in canon.formatted_address
        assert_canonical_link_invariant(locs[0])


def test_persist_neighborhood_materializes_instead_of_autolinking_city_parent() -> None:
    """Regression: child neighborhoods must not fuzzy-autolink to a broader city canonical."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-wr", project_slug="proj-wr")
        session.add(AgateRun(id="run-wr", graph_id="graph-1", status="pending"))
        session.commit()

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        chicago_canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
            geometry_json=CHICAGO_POINT,
            geometry_type="Point",
        )
        session.add(chicago_canon)
        session.commit()
        session.refresh(chicago_canon)
        chicago_id = str(chicago_canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=chicago_id,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="seed",
                suppressed=False,
            )
        )
        session.commit()

        consolidated = {
            "text": "News in West Ridge.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [
                        {
                            "id": "nominatim:wr",
                            "original_text": "West Ridge",
                            "location": "West Ridge, Chicago, IL",
                            "type": "neighborhood",
                            "geocode": {
                                "geocode_type": "nominatim",
                                "result": {
                                    "id": "nominatim:wr",
                                    "formatted_address": (
                                        "West Ridge, Chicago, Rogers Park Township, "
                                        "Cook County, Illinois, United States"
                                    ),
                                    "geometry": WGP_POINT,
                                },
                            },
                        }
                    ],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-wr",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert locs[0].stylebook_location_canonical_id is not None
        assert locs[0].stylebook_location_canonical_id != chicago_id

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 2

        reasons = locs[0].canonical_review_reasons_json
        assert isinstance(reasons, list) and reasons
        assert reasons[0].get("code") == "materialized_new_canonical"
        assert reasons[0].get("match_basis") == "string_only"
        assert reasons[0].get("head_anchor_gate_applied") is True
        assert_canonical_link_invariant(locs[0])


def test_persist_place_materializes_instead_of_autolinking_city_parent() -> None:
    """``place`` rows must not string-fuzzy-autolink to a broader ``City, ST`` canonical."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-mhs", project_slug="proj-mhs")
        session.add(AgateRun(id="run-mhs", graph_id="graph-1", status="pending"))
        session.commit()

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        chicago_canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
            geometry_json=CHICAGO_POINT,
            geometry_type="Point",
        )
        session.add(chicago_canon)
        session.commit()
        session.refresh(chicago_canon)
        chicago_id = str(chicago_canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=chicago_id,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="seed",
                suppressed=False,
            )
        )
        session.commit()

        consolidated = {
            "text": "Events at Mather High School.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    {
                        "id": "h3:mather",
                        "original_text": "Mather High School",
                        "location": "Mather High School, Chicago, IL",
                        "type": "place",
                        "geocode": {
                            "geocode_type": "pelias_structured",
                            "result": {
                                "id": "oa:mather",
                                "formatted_address": (
                                    "5835 North Lincoln Avenue, North Side, Chicago, IL, USA"
                                ),
                                "geometry": WGP_POINT,
                            },
                        },
                    }
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-mhs",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].location_type == "place"
        assert locs[0].canonical_link_status == CANONICAL_LINK_LINKED
        assert locs[0].stylebook_location_canonical_id != chicago_id

        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 2

        reasons = locs[0].canonical_review_reasons_json
        assert isinstance(reasons, list) and reasons
        assert reasons[0].get("code") == "materialized_new_canonical"
        assert reasons[0].get("match_basis") == "string_only"
        assert reasons[0].get("head_anchor_gate_applied") is True
        assert_canonical_link_invariant(locs[0])


def test_persist_defers_intersection_without_geometry_when_no_match() -> None:
    """Intersections never auto-materialize canonicals; without a match they defer."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-xsect", project_slug="proj-xsect")
        session.add(AgateRun(id="run-xsect", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Crash at Main St and Oak Ave.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    {
                        "id": "pt:1",
                        "original_text": "Main St and Oak Ave",
                        "location": "Main St and Oak Ave, Chicago, IL",
                        "type": "intersection_road",
                        "geocode": {
                            "geocode_type": "geocodio",
                            "result": {
                                "id": "gc:xsect",
                                "formatted_address": "Main St & Oak Ave, Chicago, IL",
                            },
                        },
                    }
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-xsect",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 0


def test_persist_defers_intersection_even_with_resolved_geometry() -> None:
    """Resolved geocode + geometry no longer auto-materializes intersection canonicals."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-xsect-geo", project_slug="proj-xsect-geo"
        )
        session.add(AgateRun(id="run-xsect-geo", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Crash at Main St and Oak Ave.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    {
                        "id": "pt:1",
                        "original_text": "Main St and Oak Ave",
                        "location": "Main St and Oak Ave, Chicago, IL",
                        "type": "intersection_road",
                        "geocode": {
                            "geocode_type": "geocodio",
                            "result": {
                                "id": "gc:xsect-geo",
                                "formatted_address": "Main St & Oak Ave, Chicago, IL",
                                "geometry": CHICAGO_POINT,
                            },
                        },
                    }
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-xsect-geo",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 0


def test_persist_defers_street_road_span_type_without_geometry_when_no_match() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-span", project_slug="proj-span")
        session.add(AgateRun(id="run-span", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Along Western Ave.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [
                        {
                            "id": "span:1",
                            "original_text": "Western Ave",
                            "location": "Western Ave, Chicago, IL",
                            "type": "street_road",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:western",
                                    "formatted_address": "Western Ave, Chicago, IL",
                                },
                            },
                        }
                    ],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-span",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 0


def test_persist_does_not_materialize_canonical_when_geocode_failed() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-fail", project_slug="proj-fail")
        session.add(AgateRun(id="run-fail", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Somewhere in Nowhereville.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:nv",
                            "original_text": "Nowhereville",
                            "location": "Nowhereville, XX",
                            "type": "city",
                            "geocoded": False,
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-fail",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        canon_rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(canon_rows) == 0


def test_db_output_invalid_stylebook_id_raises() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-bad-sb", project_slug="proj-bad-sb")
        session.add(AgateRun(id="run-bad", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        try:
            persist_from_consolidated(
                session,
                project_id=project_id,
                graph_id="graph-1",
                run_id="run-bad",
                consolidated=consolidated,
                db_output_params={"stylebook_id": 999_999},
            )
        except RuntimeError as exc:
            assert "DBOutput stylebook resolution failed" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_db_output_invalid_stylebook_id_skipped_when_matching_disabled() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-bad-sb-off", project_slug="proj-bad-sb-off"
        )
        session.add(AgateRun(id="run-bad-off", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-bad-off",
            consolidated=consolidated,
            db_output_params={
                "stylebook_matching_enabled": False,
                "stylebook_id": 999_999,
            },
        )
        session.commit()

        assert result.article_id is not None
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_UNLINKED
        assert locs[0].stylebook_location_canonical_id is None


def test_persist_auto_apply_false_exact_alias_leaves_pending_with_suggestion() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-aa", project_slug="proj-aa")
        session.add(AgateRun(id="run-aa", graph_id="graph-1", status="pending"))
        session.commit()

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il-aa",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="seed",
                suppressed=False,
            )
        )
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "description": "Setting",
                            "role_in_story": "Setting",
                            "nature": "primary",
                            "nature_secondary_tags": [],
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:other",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-aa",
            consolidated=consolidated,
            db_output_params={
                "stylebook_id": sb_id,
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": False,
                "adjudication_model": "gpt-5-nano",
            },
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocation

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        assert locs[0].stylebook_location_canonical_id is None
        raw = locs[0].canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(isinstance(x, dict) and x.get("code") == "canonical_suggestion" for x in raw)
        sug = next(
            x for x in raw if isinstance(x, dict) and x.get("code") == "canonical_suggestion"
        )
        assert sug.get("suggested_action") == "link_existing"
        assert sug.get("stylebook_location_canonical_id") == cid


def test_replace_article_geography_disposes_orphan_linked_substrate_without_requeue() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-repl", project_slug="proj-repl")
        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)

        art = SubstrateArticle(project_id=project_id, headline="H", text="Story in Chicago.")
        session.add(art)
        session.commit()
        session.refresh(art)
        aid = int(art.id)

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-repl",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        loc = SubstrateLocation(
            project_id=project_id,
            name="Chicago",
            normalized_name="chicago",
            stylebook_location_canonical_id=cid,
            canonical_link_status=CANONICAL_LINK_LINKED,
            source_details_json={"run_id": "run-old", "raw_entry_id": "city:1"},
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        lid = int(loc.id)

        mention = SubstrateLocationMention(
            article_id=aid,
            location_id=lid,
            deleted=False,
        )
        session.add(mention)
        session.commit()
        session.refresh(mention)
        mid = int(mention.id)

        stats = replace_machine_geography_for_article(
            session,
            project_id=project_id,
            article_id=aid,
            stylebook_id=sb_id,
        )
        session.commit()
        assert stats.mentions_cleared == 1
        assert stats.substrates_disposed == 1

    with Session(engine) as session:
        m = session.get(SubstrateLocationMention, mid)
        assert m is not None
        assert m.deleted is True
        assert session.get(SubstrateLocation, lid) is None
        canon = session.get(StylebookLocationCanonical, cid)
        assert canon is not None


def test_replace_article_geography_keeps_substrate_when_other_stories_mention() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-repl2", project_slug="proj-repl2")
        art_a = SubstrateArticle(project_id=project_id, headline="A", text="Story A.")
        art_b = SubstrateArticle(project_id=project_id, headline="B", text="Story B.")
        session.add(art_a)
        session.add(art_b)
        session.commit()
        session.refresh(art_a)
        session.refresh(art_b)
        aid_a = int(art_a.id)
        aid_b = int(art_b.id)

        loc = SubstrateLocation(
            project_id=project_id,
            name="Shared",
            normalized_name="shared",
            canonical_link_status=CANONICAL_LINK_LINKED,
            stylebook_location_canonical_id=None,
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        lid = int(loc.id)
        session.add(
            SubstrateLocationMention(article_id=aid_a, location_id=lid, deleted=False)
        )
        session.add(
            SubstrateLocationMention(article_id=aid_b, location_id=lid, deleted=False)
        )
        session.commit()

        stats = replace_machine_geography_for_article(
            session,
            project_id=project_id,
            article_id=aid_a,
        )
        session.commit()
        assert stats.mentions_cleared == 1
        assert stats.substrates_disposed == 0

    with Session(engine) as session:
        row = session.get(SubstrateLocation, lid)
        assert row is not None
        active = session.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.location_id == lid,
                SubstrateLocationMention.deleted == False,  # noqa: E712
            )
        ).all()
        assert len(active) == 1
        assert int(active[0].article_id) == aid_b


def test_replace_then_persist_revives_active_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    consolidated = {
        "text": "Hello Chicago.",
        "places": {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [
                    {
                        "id": "city:1",
                        "original_text": "Chicago",
                        "description": "Setting",
                        "location": "Chicago, IL",
                        "type": "city",
                        "geocode": {
                            "geocode_type": "pelias",
                            "result": {
                                "id": "pelias:repl",
                                "formatted_address": "Chicago, IL, USA",
                                "geometry": CHICAGO_POINT,
                            },
                        },
                    }
                ],
                "neighborhoods": [],
                "regions": [],
                "other": [],
            },
            "points": [],
            "needs_review": [],
        },
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-rev", project_slug="proj-rev")
        session.add(AgateRun(id="run-rev", graph_id="graph-rev", status="pending"))
        session.commit()

        _, _, _, stats0 = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-rev",
            run_id="run-rev",
            consolidated=consolidated,
        )
        assert stats0 is None
        session.commit()

        art = session.exec(
            select(SubstrateArticle).where(SubstrateArticle.project_id == project_id)
        ).one()
        aid = int(art.id)
        mention = session.exec(
            select(SubstrateLocationMention).where(SubstrateLocationMention.article_id == aid)
        ).one()
        mention.deleted = True
        session.add(mention)
        session.commit()
        mid = int(mention.id)

        _, _, _, stats1 = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-rev",
            run_id="run-rev-2",
            consolidated=consolidated,
            replace_machine_geography=True,
        )
        assert stats1 is not None
        assert stats1.mentions_cleared >= 0
        session.commit()

    with Session(engine) as session:
        m = session.get(SubstrateLocationMention, mid)
        assert m is not None
        assert m.deleted is False


def test_upsert_mention_undeletes_existing_row() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    consolidated = {
        "text": "Hello Chicago.",
        "places": {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [
                    {
                        "id": "city:1",
                        "original_text": "Chicago",
                        "description": "Setting",
                        "location": "Chicago, IL",
                        "type": "city",
                        "geocode": {
                            "geocode_type": "pelias",
                            "result": {
                                "id": "pelias:undelete",
                                "formatted_address": "Chicago, IL, USA",
                                "geometry": CHICAGO_POINT,
                            },
                        },
                    }
                ],
                "neighborhoods": [],
                "regions": [],
                "other": [],
            },
            "points": [],
            "needs_review": [],
        },
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-und", project_slug="proj-und")
        session.add(AgateRun(id="run-und", graph_id="graph-und", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-und",
            run_id="run-und",
            consolidated=consolidated,
        )
        session.commit()

        art = session.exec(
            select(SubstrateArticle).where(SubstrateArticle.project_id == project_id)
        ).one()
        mention = session.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.article_id == int(art.id)
            )
        ).one()
        mention.deleted = True
        session.add(mention)
        session.commit()
        mid = int(mention.id)

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-und",
            run_id="run-und-2",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        m = session.get(SubstrateLocationMention, mid)
        assert m is not None
        assert m.deleted is False


def _neighborhood_entry(
    *,
    entry_id: str,
    name: str,
    canonical_id: str,
    geometry: dict,
    formatted_address: str | None = None,
) -> dict:
    return {
        "id": entry_id,
        "original_text": name.split(",")[0],
        "location": name,
        "type": "neighborhood",
        "components": {
            "neighborhood": name.split(",")[0].strip(),
            "city": "Chicago",
            "state": {"abbr": "IL"},
        },
        "geocode": {
            "geocode_type": "canonical_db",
            "result": {
                "id": f"stylebook:{canonical_id}",
                "canonical_id": canonical_id,
                "formatted_address": formatted_address or name,
                "geometry": geometry,
            },
        },
    }


def test_poisoned_neighborhood_candidate_id_does_not_collapse_bucktown_uptown() -> None:
    """Distinct neighborhood names must not share one substrate row via a poisoned UUID."""
    uptown_uuid = "b711d7fe-b5ce-4062-8b35-9a35114b2d48"
    bucktown_pt = {"type": "Point", "coordinates": [-87.68, 41.92]}
    uptown_pt = {"type": "Point", "coordinates": [-87.65, 41.97]}
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _places(entries: list[dict]) -> dict:
        return {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [],
                "neighborhoods": entries,
                "regions": [],
                "other": [],
            },
            "points": [],
            "needs_review": [],
        }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-buck", project_slug="proj-buck")
        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        for label, slug, geom in (
            ("Bucktown, Chicago, IL", "bucktown-chicago-il", bucktown_pt),
            ("Uptown, Chicago, IL", "uptown-chicago-il", uptown_pt),
        ):
            session.add(
                StylebookLocationCanonical(
                    stylebook_id=sb_id,
                    label=label,
                    slug=slug,
                    location_type="neighborhood",
                    status="active",
                    geometry_json=geom,
                    geometry_type="Point",
                    formatted_address=label,
                )
            )
        session.add(AgateRun(id="run-buck-a", graph_id="graph-buck", status="pending"))
        session.add(AgateRun(id="run-buck-b", graph_id="graph-buck", status="pending"))
        session.commit()

        # Both payloads carry the Uptown candidate UUID (poisoned for Bucktown).
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-buck",
            run_id="run-buck-a",
            consolidated={
                "text": "Nightlife in Bucktown.",
                "url": "https://example.com/bucktown",
                "places": _places(
                    [
                        _neighborhood_entry(
                            entry_id="n:buck",
                            name="Bucktown, Chicago, IL",
                            canonical_id=uptown_uuid,
                            geometry=bucktown_pt,
                        )
                    ]
                ),
            },
            db_output_params={"auto_apply_canonicalization": True, "stylebook_id": sb_id},
        )
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-buck",
            run_id="run-buck-b",
            consolidated={
                "text": "A story from Uptown.",
                "url": "https://example.com/uptown",
                "places": _places(
                    [
                        _neighborhood_entry(
                            entry_id="n:up",
                            name="Uptown, Chicago, IL",
                            canonical_id=uptown_uuid,
                            geometry=uptown_pt,
                        )
                    ]
                ),
            },
            db_output_params={"auto_apply_canonicalization": True, "stylebook_id": sb_id},
        )
        session.commit()

        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 2
        by_name = {str(loc.name): loc for loc in locs}
        assert "Bucktown, Chicago, IL" in by_name
        assert "Uptown, Chicago, IL" in by_name
        assert by_name["Bucktown, Chicago, IL"].external_id == (
            f"stylebook:{uptown_uuid}:bucktown-chicago-il"
        )
        assert by_name["Uptown, Chicago, IL"].external_id == (
            f"stylebook:{uptown_uuid}:uptown-chicago-il"
        )


def test_linked_neighborhood_mismatch_skips_alias_refresh_and_replans() -> None:
    """Already-linked rows that no longer match their FK must not refresh aliases."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    bucktown_pt = {"type": "Point", "coordinates": [-87.68, 41.92]}
    uptown_pt = {"type": "Point", "coordinates": [-87.65, 41.97]}

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-relink", project_slug="proj-relink")
        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        ws = session.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)

        bucktown = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Bucktown, Chicago, IL",
            slug="bucktown-chicago-il",
            location_type="neighborhood",
            status="active",
            geometry_json=bucktown_pt,
            geometry_type="Point",
            formatted_address="Bucktown, Chicago, IL",
        )
        uptown = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Uptown, Chicago, IL",
            slug="uptown-chicago-il",
            location_type="neighborhood",
            status="active",
            geometry_json=uptown_pt,
            geometry_type="Point",
            formatted_address="Uptown, Chicago, IL",
        )
        session.add(bucktown)
        session.add(uptown)
        session.commit()
        session.refresh(bucktown)
        session.refresh(uptown)
        bucktown_id = str(bucktown.id)
        uptown_id = str(uptown.id)

        # Corrupted linked row: Uptown name + Bucktown FK, shared poisoned external id.
        loc = SubstrateLocation(
            project_id=project_id,
            name="Uptown, Chicago, IL",
            normalized_name="uptown, chicago, il",
            location_type="neighborhood",
            status="active",
            external_source="stylebook_location",
            external_id=f"stylebook:{bucktown_id}:uptown-chicago-il",
            identity_fingerprint="fp-uptown-corrupt",
            formatted_address="Uptown, Chicago, IL",
            geometry_json=uptown_pt,
            geometry_type="Point",
            stylebook_location_canonical_id=bucktown_id,
            canonical_link_status=CANONICAL_LINK_LINKED,
            source_kind="agate_geocode",
        )
        session.add(loc)
        session.add(AgateRun(id="run-relink", graph_id="graph-relink", status="pending"))
        session.commit()
        session.refresh(loc)
        loc_id = int(loc.id)  # type: ignore[arg-type]

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-relink",
            run_id="run-relink",
            consolidated={
                "text": "A story from Uptown.",
                "url": "https://example.com/uptown-relink",
                "places": {
                    "areas": {
                        "states": [],
                        "counties": [],
                        "cities": [],
                        "neighborhoods": [
                            _neighborhood_entry(
                                entry_id="n:up-relink",
                                name="Uptown, Chicago, IL",
                                canonical_id=bucktown_id,
                                geometry=uptown_pt,
                            )
                        ],
                        "regions": [],
                        "other": [],
                    },
                    "points": [],
                    "needs_review": [],
                },
            },
            db_output_params={"auto_apply_canonicalization": True, "stylebook_id": sb_id},
        )
        session.commit()

        refreshed = session.get(SubstrateLocation, loc_id)
        assert refreshed is not None
        # Must not keep the Bucktown FK or write Uptown aliases onto Bucktown.
        assert refreshed.stylebook_location_canonical_id != bucktown_id
        aliases = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == bucktown_id,
            )
        ).all()
        assert not any("uptown" in str(a.normalized_alias) for a in aliases)
        if refreshed.stylebook_location_canonical_id is not None:
            assert str(refreshed.stylebook_location_canonical_id) == uptown_id
