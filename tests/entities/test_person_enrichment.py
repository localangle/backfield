"""Person enrichment cache reuse and empty-only metadata writes."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstratePerson,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.entities.person.enrichment import (
    cached_selected_links,
    fill_empty_person_enrichment_meta,
)
from backfield_entities.entities.person.persist import apply_canonical_persist_plan
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate.entities.person.upsert import _upsert_person

from tests.project_helpers import project_ownership_fields


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-person-enrich")
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
        slug="demo-person-enrich",
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
    affiliation: str,
    links: dict[str, str],
) -> str:
    canon = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label=label,
        slug=slug,
        affiliation=affiliation,
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
            StylebookPersonMeta(
                project_id=project_id,
                stylebook_person_canonical_id=canonical_id,
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
            label="Harold Washington",
            slug="harold-washington",
            affiliation="Chicago",
            links={
                "wikidata_id": "Q295584",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Harold_Washington",
            },
        )
        found = cached_selected_links(
            session,
            stylebook_id=sb_id,
            name="Harold Washington",
            affiliation="Chicago",
            sources={"wikidata", "wikipedia"},
            project_id=pid,
        )
        assert found == {
            "wikidata_id": "Q295584",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Harold_Washington",
        }


def test_cached_links_skip_ambiguous_and_incomplete_canonicals() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Steve Stone",
            slug="steve-stone-1",
            affiliation="Chicago",
            links={"wikidata_id": "Q1", "wikipedia_url": "https://en.wikipedia.org/wiki/One"},
        )
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Steve Stone",
            slug="steve-stone-2",
            affiliation="Chicago",
            links={"wikidata_id": "Q2", "wikipedia_url": "https://en.wikipedia.org/wiki/Two"},
        )
        assert (
            cached_selected_links(
                session,
                stylebook_id=sb_id,
                name="Steve Stone",
                affiliation="Chicago",
                sources={"wikidata", "wikipedia"},
                project_id=pid,
            )
            is None
        )
        _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Ada Lovelace",
            slug="ada-lovelace",
            affiliation="London",
            links={"wikidata_id": "Q7259"},
        )
        assert (
            cached_selected_links(
                session,
                stylebook_id=sb_id,
                name="Ada Lovelace",
                affiliation="London",
                sources={"wikidata", "wikipedia"},
                project_id=pid,
            )
            is None
        )
        assert cached_selected_links(
            session,
            stylebook_id=sb_id,
            name="Ada Lovelace",
            affiliation="London",
            sources={"wikidata"},
            project_id=pid,
        ) == {"wikidata_id": "Q7259"}


def test_meta_fill_does_not_overwrite_existing_text() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canonical_id = _canonical(
            session,
            stylebook_id=sb_id,
            project_id=pid,
            label="Harold Washington",
            slug="harold-washington",
            affiliation="Chicago",
            links={"wikidata_id": "QOLD"},
        )
        fill_empty_person_enrichment_meta(
            session,
            project_id=pid,
            canonical_id=canonical_id,
            links={
                "wikidata_id": "QNEW",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Harold_Washington",
            },
        )
        session.commit()
        rows = session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == canonical_id
            )
        ).all()
        by_type = {row.meta_type: row.value_text for row in rows}
        assert by_type["wikidata"] == "QOLD"
        assert by_type["wikipedia"] == "https://en.wikipedia.org/wiki/Harold_Washington"


def test_materialize_copies_links_onto_empty_metadata() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="New Person",
            normalized_name="new person",
            affiliation="Springfield",
            source_details_json={
                "wikidata_id": "Q123",
                "wikipedia_url": "https://en.wikipedia.org/wiki/New_Person",
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        apply_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            person=person,
            plan=CanonicalPersistPlan(decision=CanonicalPersistDecision.MATERIALIZE_NEW),
            people_bucket="ready",
        )
        session.commit()
        session.refresh(person)
        canonical_id = str(person.stylebook_person_canonical_id)
        rows = session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == canonical_id
            )
        ).all()
        by_type = {row.meta_type: row.value_text for row in rows}
        assert by_type["wikidata"] == "Q123"
        assert by_type["wikipedia"] == "https://en.wikipedia.org/wiki/New_Person"


def test_upsert_stores_links_and_keeps_them_when_a_later_entry_omits_them() -> None:
    engine = _engine()
    with Session(engine) as session:
        _sb_id, pid = _seed(session)
        entry = {
            "name": "Harold Washington",
            "affiliation": "Chicago",
            "public_figure": True,
            "wikidata_id": "Q295584",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Harold_Washington",
        }
        created = _upsert_person(
            session,
            project_id=pid,
            bucket="ready",
            entry=entry,
            run_id="run-1",
            graph_id="graph-1",
        )
        assert created is not None
        session.commit()
        details = created.person.source_details_json
        assert isinstance(details, dict)
        assert details["wikidata_id"] == "Q295584"
        assert details["wikipedia_url"] == "https://en.wikipedia.org/wiki/Harold_Washington"

        again = _upsert_person(
            session,
            project_id=pid,
            bucket="ready",
            entry={"name": "Harold Washington", "affiliation": "Chicago", "public_figure": True},
            run_id="run-2",
            graph_id="graph-1",
            update_existing=True,
        )
        assert again is not None
        session.commit()
        session.refresh(again.person)
        kept = again.person.source_details_json
        assert isinstance(kept, dict)
        assert kept["wikidata_id"] == "Q295584"
        assert kept["wikipedia_url"] == "https://en.wikipedia.org/wiki/Harold_Washington"
