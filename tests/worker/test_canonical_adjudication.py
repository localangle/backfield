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
from worker.canonical_adjudication import adjudicate_ambiguous_plan_with_llm


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
            primary_substrate_location_id=None,
            status="active",
        )
        c2 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Beta Place",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.add(c2)
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        id1 = int(c1.id)  # type: ignore[arg-type]
        id2 = int(c2.id)  # type: ignore[arg-type]

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
                f'{{"canonical_id": {id1}, "confidence": 0.92, '
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


def test_adjudicate_ambiguous_materialize_when_llm_rejects_link(monkeypatch) -> None:
    """Declined link + materialize-eligible row becomes MATERIALIZE_NEW (review UI suggestion)."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        pid, sb_id = _bootstrap(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin, TX",
            primary_substrate_location_id=None,
            status="active",
        )
        session.add(c1)
        session.commit()
        session.refresh(c1)
        id1 = int(c1.id)  # type: ignore[arg-type]

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
