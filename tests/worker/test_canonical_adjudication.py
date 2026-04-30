from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from sqlmodel import Session, SQLModel, create_engine
from worker.canonical_adjudication import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    adjudicate_ambiguous_plan_with_llm,
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

        monkeypatch.setattr("worker.canonical_adjudication.call_llm", _fake_llm)

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

        monkeypatch.setattr("worker.canonical_adjudication.call_llm", _fake_llm)

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

        monkeypatch.setattr("worker.canonical_adjudication.call_llm", _fake_llm)

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

        monkeypatch.setattr("worker.canonical_adjudication.call_llm", _fake_llm)

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
        "worker.canonical_adjudication.link_pair_allowed",
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

        monkeypatch.setattr("worker.canonical_adjudication.call_llm", _fake_llm)

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
