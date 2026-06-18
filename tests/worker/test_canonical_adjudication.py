from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstratePerson,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.entities.location.policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate.canonical.adjudication import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    adjudicate_ambiguous_plan_with_llm,
)
from worker.substrate.entities.person.adjudication import (
    adjudicate_ambiguous_person_plan_with_llm,
    prepare_person_adjudication,
)


def _bootstrap(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="O", slug="o-adj")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid,
        stylebook_id=sb_id,
        name="W",
        slug="w-adj",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    proj = BackfieldProject(
        organization_id=oid,
        name="P",
        slug="p-adj",
        workspace_id=int(ws.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(proj.id), sb_id  # type: ignore[arg-type]


def test_adjudicate_ambiguous_upgrades_when_llm_confident(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Alpha Place",
            slug="alpha-place",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        c2 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Beta Place",
            slug="beta-place",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.add(c2)
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        id1 = str(c1.id)
        id2 = str(c2.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Alpha Place, Minneapolis, MN",
            normalized_name="alpha place, minneapolis, mn",
            location_type="place",
            identity_fingerprint="fp-adj-1",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": id1,
                    "best_score": 0.5,
                    "recall_canonical_ids": [id1, id2],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{id1}", "confidence": 0.92, '
                f'"rationale": "Name matches Alpha."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.LINK_EXISTING
        assert out.existing_canonical_id == id1
        codes = [str(r.get("code") or "") for r in out.resolution_reasons]
        assert "ambiguous_canonical_match" in codes
        assert "canonical_adjudication" in codes
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("min_confidence_for_link") == ADJUDICATION_LINK_MIN_CONFIDENCE


def test_adjudicate_ambiguous_materialize_when_llm_rejects_link(monkeypatch) -> None:
    """Declined link + materialize-eligible row becomes MATERIALIZE_NEW (review UI suggestion)."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin, TX",
            slug="austin-tx",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Austin, AR",
            normalized_name="austin, ar",
            location_type="city",
            identity_fingerprint="fp-adj-ar",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": id1,
                    "best_score": 0.8,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                '{"canonical_id": null, "confidence": 0.15, '
                '"rationale": "AR vs TX; no fit."}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        codes = [str(r.get("code") or "") for r in out.resolution_reasons]
        assert "ambiguous_canonical_match" in codes
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "no_high_confidence_link"


def test_adjudicate_ambiguous_person_materialize_when_llm_rejects_link(monkeypatch) -> None:
    """Greg Abbott–style namesake recall: declined link materializes when review gates allow."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        wrong = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Other Person",
            slug="other-person",
            affiliation="Elsewhere",
            status="active",
        )
        session.add(wrong)
        session.commit()
        session.refresh(wrong)
        wrong_id = str(wrong.id)

        person = SubstratePerson(
            project_id=pid,
            name="Greg Abbott",
            normalized_name="greg abbott",
            title="Governor",
            affiliation="State of Texas",
            identity_fingerprint="fp-adj-greg",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_person_canonical_match",
                    "best_canonical_id": wrong_id,
                    "recall_canonical_ids": [wrong_id],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                '{"canonical_id": null, "confidence": 0.33, '
                '"rationale": "None match Greg Abbott, Governor of Texas."}'
            )

        monkeypatch.setattr(
            "worker.substrate.entities.person.adjudication.call_llm",
            _fake_llm,
        )

        out = adjudicate_ambiguous_person_plan_with_llm(
            session,
            plan=plan,
            person=person,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        codes = [str(r.get("code") or "") for r in out.resolution_reasons]
        assert "ambiguous_person_canonical_match" in codes
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "no_high_confidence_link"
        assert adj.get("canonical_id") is None


def test_adjudicate_ambiguous_person_athlete_defers_when_llm_rejects_link(monkeypatch) -> None:
    """Athletes defer on declined link instead of minting a duplicate canonical."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        braves = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Luisangel Acuña",
            slug="luisangel-acuna",
            affiliation="Atlanta Braves",
            person_type="athlete",
            status="active",
        )
        session.add(braves)
        session.commit()
        session.refresh(braves)
        braves_id = str(braves.id)

        person = SubstratePerson(
            project_id=pid,
            name="Luisangel Acuña",
            normalized_name="luisangel acuña",
            title="shortstop",
            affiliation="New York Mets",
            person_type="athlete",
            public_figure=True,
            identity_fingerprint="fp-adj-acuna",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_person_canonical_match",
                    "recall_canonical_ids": [braves_id],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                '{"canonical_id": null, "confidence": 0.4, '
                '"rationale": "Different team but likely same athlete."}'
            )

        monkeypatch.setattr(
            "worker.substrate.entities.person.adjudication.call_llm",
            _fake_llm,
        )

        out = adjudicate_ambiguous_person_plan_with_llm(
            session,
            plan=plan,
            person=person,
            stylebook_id=sb_id,
            model="gpt-5-nano",
            article_text="Former Brave Luisangel Acuña drove in a run for the Mets.",
            mention_texts=["Luisangel Acuña"],
        )

        assert out.decision == CanonicalPersistDecision.DEFER


def test_prepare_person_adjudication_includes_athlete_context(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Luisangel Acuña",
            slug="luisangel-acuna-braves",
            affiliation="Atlanta Braves",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        canon_id = str(canon.id)

        person = SubstratePerson(
            project_id=pid,
            name="Luisangel Acuña",
            normalized_name="luisangel acuña",
            affiliation="New York Mets",
            person_type="athlete",
            public_figure=True,
            identity_fingerprint="fp-adj-prompt",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_person_canonical_match",
                    "recall_canonical_ids": [canon_id],
                },
            ),
        )

        prepared = prepare_person_adjudication(
            session,
            plan=plan,
            person=person,
            stylebook_id=sb_id,
            model="gpt-5-nano",
            article_text="Former Brave Luisangel Acuña drove in a run for the Mets.",
            mention_texts=["Luisangel Acuña"],
        )
        assert prepared is not None
        assert "Person type: 'athlete'" in prepared.prompt
        assert "Public figure: True" in prepared.prompt
        assert "team (affiliation) and position (title) change over time" in prepared.prompt
        assert "Former Brave Luisangel Acuña" in prepared.prompt


def test_adjudicate_ambiguous_person_stays_deferred_when_flag_review(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        wrong = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Other Person",
            slug="other-person-flag",
            status="active",
        )
        session.add(wrong)
        session.commit()
        session.refresh(wrong)
        wrong_id = str(wrong.id)

        person = SubstratePerson(
            project_id=pid,
            name="Prince",
            normalized_name="prince",
            identity_fingerprint="fp-adj-prince",
            source_details_json={
                "review_handling": "flag_review",
                "review_reason_code": "stage_name_or_alias",
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_person_canonical_match",
                    "recall_canonical_ids": [wrong_id],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return '{"canonical_id": null, "confidence": 0.1, "rationale": "No match."}'

        monkeypatch.setattr(
            "worker.substrate.entities.person.adjudication.call_llm",
            _fake_llm,
        )

        out = adjudicate_ambiguous_person_plan_with_llm(
            session,
            plan=plan,
            person=person,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.DEFER


def test_adjudicate_rejects_link_when_confidence_below_floor(monkeypatch) -> None:
    """Same-place pick is ignored when confidence is below the link threshold (0.9)."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Alpha Place",
            slug="alpha-place-lowconf",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Alpha Place, Minneapolis, MN",
            normalized_name="alpha place, minneapolis, mn",
            location_type="place",
            identity_fingerprint="fp-adj-lowconf",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": id1,
                    "best_score": 0.5,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{id1}", "confidence": 0.85, '
                f'"rationale": "Probably the same POI."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "no_high_confidence_link"
        assert adj.get("canonical_id") == id1


def test_adjudicate_accepts_link_at_exact_min_confidence(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Gamma City",
            slug="gamma-city",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Gamma City",
            normalized_name="gamma city",
            location_type="city",
            identity_fingerprint="fp-adj-edge",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": id1,
                    "best_score": 0.5,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{id1}", "confidence": {ADJUDICATION_LINK_MIN_CONFIDENCE}, '
                f'"rationale": "Exact label match."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.LINK_EXISTING
        assert out.existing_canonical_id == id1


def test_adjudicate_rejects_llm_choice_when_link_pair_denied(monkeypatch) -> None:
    """High-confidence LLM pick is ignored when :func:`link_pair_allowed` returns False."""
    monkeypatch.setattr(
        "worker.substrate.canonical.adjudication.link_pair_allowed",
        lambda _s, _c: False,
    )
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c_city = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c_city)
        session.commit()
        session.refresh(c_city)
        cid = str(c_city.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Learning Resources, Vernon Hills, IL",
            normalized_name="learning resources, vernon hills, il",
            location_type="place",
            identity_fingerprint="fp-adj-type",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": cid,
                    "best_score": 0.9,
                    "recall_canonical_ids": [cid],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{cid}", "confidence": 0.95, '
                f'"rationale": "Name overlap."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "no_high_confidence_link"


def test_adjudicate_rejects_llm_choice_when_content_sanity_blocks(monkeypatch) -> None:
    """High-confidence LLM pick is coerced when POI identity is absent from the canonical label."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        park = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Jackson Park, Chicago, IL",
            slug="jackson-park-chicago-il",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(park)
        session.commit()
        session.refresh(park)
        park_id = str(park.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Tafari's Kitchen, Jackson Park, Chicago, IL",
            normalized_name="tafari's kitchen, jackson park, chicago, il",
            location_type="place",
            identity_fingerprint="fp-adj-tafari",
            source_details_json={
                "place_extract_components": {
                    "place": {"name": "Tafari's Kitchen", "addressable": True},
                    "city": "Chicago",
                }
            },
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": "ambiguous_canonical_match",
                    "best_canonical_id": park_id,
                    "best_score": 0.28,
                    "gate_demoted_recall_match": True,
                    "recall_canonical_ids": [park_id],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{park_id}", "confidence": 0.92, '
                f'"rationale": "Substrate mentions Jackson Park."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "content_sanity_coerced"
        assert adj.get("canonical_id") == park_id


def test_adjudicate_political_district_fuzzy_plan_runs_llm(monkeypatch) -> None:
    """``linked_fuzzy_autolink`` + political_district is adjudicated like ambiguity."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 8, Chicago, IL",
            slug="ward-8-chi",
            location_type="political_district",
            district_key="US-WARD-IL-8",
            district_kind="ward",
            district_number="8",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Eighth Ward, Chicago, IL",
            normalized_name="eighth ward, chicago, il",
            location_type="political_district",
            identity_fingerprint="fp-adj-pd",
            source_details_json={
                "place_extract_components": {
                    "district": {"kind": "ward", "number": "8"},
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.LINK_EXISTING,
            existing_canonical_id=id1,
            resolution_reasons=(
                {
                    "code": "linked_fuzzy_autolink",
                    "canonical_id": id1,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(prompt: str, *_a, **_k) -> str:
            assert "District identity key" in prompt
            assert "US-WARD-IL-8" in prompt
            return (
                f'{{"canonical_id": "{id1}", "confidence": 0.95, '
                f'"rationale": "Same ward number and city."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.LINK_EXISTING
        assert out.existing_canonical_id == id1


def test_adjudicate_political_district_coerces_when_district_key_mismatch(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 7, Chicago, IL",
            slug="ward-7-chi",
            location_type="political_district",
            district_key="US-WARD-IL-7",
            district_kind="ward",
            district_number="7",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = str(c1.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="Ward 8, Chicago, IL",
            normalized_name="ward 8, chicago, il",
            location_type="political_district",
            identity_fingerprint="fp-adj-pd2",
            source_details_json={
                "place_extract_components": {
                    "district": {"kind": "ward", "number": "8"},
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        plan = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.LINK_EXISTING,
            existing_canonical_id=id1,
            resolution_reasons=(
                {
                    "code": "linked_fuzzy_autolink",
                    "canonical_id": id1,
                    "recall_canonical_ids": [id1],
                },
            ),
        )

        def _fake_llm(*_a, **_k) -> str:
            return (
                f'{{"canonical_id": "{id1}", "confidence": 0.95, '
                f'"rationale": "LLM wrongly picks nearby ward."}}'
            )

        monkeypatch.setattr("worker.substrate.canonical.adjudication.call_llm", _fake_llm)

        out = adjudicate_ambiguous_plan_with_llm(
            session,
            plan=plan,
            location=loc,
            stylebook_id=sb_id,
            model="gpt-5-nano",
        )

        assert out.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        adj = next(r for r in out.resolution_reasons if r.get("code") == "canonical_adjudication")
        assert adj.get("outcome") == "district_key_mismatch_coerced"
