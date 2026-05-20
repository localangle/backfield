from __future__ import annotations

from backfield_db import (
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook import assert_canonical_link_invariant
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate_persistence import _find_mention_span, persist_from_consolidated

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
        assert alias_rows[0].normalized_alias == locations[0].normalized_name

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
        assert locs[0].external_id == f"stylebook:{sb_uuid}"


def test_persist_stylebook_id_keeps_full_prefixed_external_id() -> None:
    sb_uuid = "660e8400-e29b-41d4-a716-446655440001"
    prefixed = f"stylebook:{sb_uuid}"
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
                                    "id": prefixed,
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
    already = f"stylebook:{sb_uuid}"
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
                                    "canonical_id": already,
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
        _, retired0 = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-r",
            run_id="run-a",
            consolidated={"text": text, "places": run1_places},
        )
        assert retired0 == 0
        _, retired1 = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-r",
            run_id="run-b",
            consolidated={"text": text, "places": run2_places},
        )
        assert retired1 == 1
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
        assert len(old_locs) == 1
        assert old_locs[0].external_id == "pelias:midway-old"


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
    """Intersection types keep strict materialization (geometry + resolved); otherwise defer."""
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
