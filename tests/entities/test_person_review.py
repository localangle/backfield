"""Person extract review routing: classifier, policy, and persist apply."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED
from backfield_entities.canonical.plan_types import CanonicalPersistDecision
from backfield_entities.entities.person.persist import (
    apply_candidate_ai_review_recommendation,
    apply_canonical_persist_plan,
)
from backfield_entities.entities.person.policy import decide_person_canonical_persist_plan
from backfield_entities.entities.person.review import (
    REASON_ANIMAL,
    REASON_CHILD,
    REASON_FIRST_NAME_ONLY,
    REASON_PSEUDONYM,
    REASON_STAGE_NAME_OR_ALIAS,
    apply_deterministic_review_overrides,
    apply_pseudonym_review_override,
    finalize_review_fields_from_entry,
    inferred_surname_from_review_message,
    looks_like_descriptive_pseudonym,
    looks_like_first_name_only_token,
    parse_review_fields_from_entry,
    person_inferred_surname_from_details,
    person_review_blocks_auto_materialize,
    person_review_recommends_defer_only,
    plan_includes_defer_only_person_review,
)
from backfield_entities.entities.person.types import person_identity_fingerprint
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-person-review")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-review", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_finalize_inferred_surname_flags_first_name_only_review() -> None:
    out = finalize_review_fields_from_entry(
        {
            "name": "Peter Wirtz",
            "surname_inferred_from_relative": True,
            "review_handling": "none",
            "mentions": [
                {
                    "text": "Rocky Wirtz's brother, Peter, attended the hearing.",
                    "quote": False,
                }
            ],
        }
    )
    assert out["review_handling"] == "flag_review"
    assert out["review_reason_code"] == REASON_FIRST_NAME_ONLY
    assert out["needs_review"] is True
    assert "inferred" in (out.get("review_message") or "").lower()


def test_finalize_first_name_only_when_llm_left_none() -> None:
    out = finalize_review_fields_from_entry(
        {
            "name": "Maria",
            "review_handling": "none",
            "mentions": [{"text": "Maria spoke at the rally.", "quote": False}],
        }
    )
    assert out["review_handling"] == "flag_review"
    assert out["review_reason_code"] == REASON_FIRST_NAME_ONLY
    assert out["needs_review"] is True


def test_llm_stage_name_alias_preserved() -> None:
    handling, code, _msg = parse_review_fields_from_entry(
        {
            "name": "Prince",
            "review_handling": "flag_review",
            "review_reason_code": REASON_STAGE_NAME_OR_ALIAS,
        }
    )
    assert handling == "flag_review"
    assert code == REASON_STAGE_NAME_OR_ALIAS
    assert not looks_like_first_name_only_token("Prince")  # mononym length > 5


def test_deterministic_does_not_override_llm_auto_defer() -> None:
    handling, code, _ = apply_deterministic_review_overrides(
        "Buddy",
        handling="auto_defer",
        reason_code=REASON_ANIMAL,
        message="Identified as an animal",
    )
    assert handling == "auto_defer"
    assert code == REASON_ANIMAL


def test_inferred_surname_from_review_message_legacy_rows() -> None:
    assert inferred_surname_from_review_message(
        "Inferred surname Bowser from son Drew Bowser"
    )
    details = {
        "review_reason_code": REASON_FIRST_NAME_ONLY,
        "review_message": "Inferred surname Bowser from son Drew Bowser",
    }
    assert person_inferred_surname_from_details(details)
    assert not person_review_recommends_defer_only(
        reason_code=REASON_FIRST_NAME_ONLY,
        source_details=details,
    )
    assert not plan_includes_defer_only_person_review(
        [
            {
                "code": REASON_FIRST_NAME_ONLY,
                "message": "Inferred surname Bowser from son Drew Bowser",
            }
        ]
    )


def test_inferred_surname_uses_link_create_path_not_defer_only() -> None:
    details = {
        "name": "Peter Wirtz",
        "surname_inferred_from_relative": True,
        "review_reason_code": REASON_FIRST_NAME_ONLY,
    }
    assert not person_review_recommends_defer_only(
        reason_code=REASON_FIRST_NAME_ONLY,
        source_details=details,
    )
    assert person_review_blocks_auto_materialize(
        reason_code=REASON_FIRST_NAME_ONLY,
        source_details=details,
    )


def test_stage_name_is_not_defer_only_but_blocks_auto_materialize() -> None:
    assert not person_review_recommends_defer_only(
        reason_code=REASON_STAGE_NAME_OR_ALIAS,
        source_details={"review_reason_code": REASON_STAGE_NAME_OR_ALIAS},
        person_name="Prince",
    )
    assert person_review_blocks_auto_materialize(
        reason_code=REASON_STAGE_NAME_OR_ALIAS,
        source_details={"review_reason_code": REASON_STAGE_NAME_OR_ALIAS},
        person_name="Prince",
    )


def test_descriptive_pseudonym_heuristic() -> None:
    assert looks_like_descriptive_pseudonym("TRUTH-TELLER IN ARKANSAS")
    assert looks_like_descriptive_pseudonym("Hurting Heart in Georgia")
    assert not looks_like_descriptive_pseudonym("Prince")
    assert not looks_like_descriptive_pseudonym("John Smith")


def test_finalize_pseudonym_from_name() -> None:
    out = finalize_review_fields_from_entry(
        {
            "name": "TRUTH-TELLER IN ARKANSAS",
            "review_handling": "none",
            "mentions": [{"text": "TRUTH-TELLER IN ARKANSAS spoke out.", "quote": False}],
        }
    )
    assert out["review_handling"] == "flag_review"
    assert out["review_reason_code"] == REASON_PSEUDONYM
    assert out["needs_review"] is True


def test_pseudonym_overrides_stage_name_code() -> None:
    handling, code, _msg = apply_pseudonym_review_override(
        "Hurting Heart in Georgia",
        handling="flag_review",
        reason_code=REASON_STAGE_NAME_OR_ALIAS,
        message="Stage name",
    )
    assert handling == "flag_review"
    assert code == REASON_PSEUDONYM


def test_policy_pseudonym_defers_with_defer_suggestion() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="TRUTH-TELLER IN ARKANSAS",
            normalized_name="truth-teller in arkansas",
            identity_fingerprint=person_identity_fingerprint(
                normalized_name="truth-teller in arkansas"
            ),
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={
                "review_handling": "flag_review",
                "review_reason_code": REASON_STAGE_NAME_OR_ALIAS,
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER
        assert any(
            isinstance(r, dict) and r.get("code") == REASON_PSEUDONYM
            for r in plan.resolution_reasons
        )
        apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        session.refresh(person)
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("suggested_action") == "defer" for x in raw
        )


def test_policy_flag_review_runs_recall_and_ai_review_suggests_create() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="Prince",
            normalized_name="prince",
            identity_fingerprint=person_identity_fingerprint(normalized_name="prince"),
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={
                "review_handling": "flag_review",
                "review_reason_code": REASON_STAGE_NAME_OR_ALIAS,
                "review_message": "Stage name",
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER
        assert any(
            isinstance(r, dict) and r.get("suggested_action") == "materialize_new"
            for r in plan.resolution_reasons
        )

        apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        session.refresh(person)
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("suggested_action") == "materialize_new" for x in raw
        )


def test_policy_first_name_only_defers_with_defer_suggestion() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="Maria",
            normalized_name="maria",
            identity_fingerprint=person_identity_fingerprint(normalized_name="maria"),
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={
                "review_handling": "flag_review",
                "review_reason_code": REASON_FIRST_NAME_ONLY,
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER
        apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        session.refresh(person)
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("suggested_action") == "defer" for x in raw
        )


def test_policy_and_apply_child_auto_waive() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="Timmy Larson",
            normalized_name="timmy larson",
            identity_fingerprint=person_identity_fingerprint(normalized_name="timmy larson"),
            source_details_json={
                "review_handling": "auto_defer",
                "review_reason_code": REASON_CHILD,
                "review_message": "Identified as a child",
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(
            session, stylebook_id=sb_id, person=person, auto_apply_canonicalization=True
        )
        assert plan.decision == CanonicalPersistDecision.DEFER
        apply_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            person=person,
            plan=plan,
            people_bucket="ready",
            auto_apply_canonicalization=True,
        )
        session.commit()
        session.refresh(person)
        assert person.canonical_link_status == CANONICAL_LINK_WAIVED
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(isinstance(x, dict) and x.get("code") == REASON_CHILD for x in raw)


def test_child_ai_review_recommends_defer() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="Timmy Larson",
            normalized_name="timmy larson",
            identity_fingerprint=person_identity_fingerprint(normalized_name="timmy larson"),
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={
                "review_handling": "auto_defer",
                "review_reason_code": REASON_CHILD,
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        session.refresh(person)
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("suggested_action") == "defer" for x in raw
        )


def test_policy_flag_review_stays_pending_on_apply() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        person = SubstratePerson(
            project_id=pid,
            name="Prince",
            normalized_name="prince",
            identity_fingerprint=person_identity_fingerprint(normalized_name="prince"),
            canonical_link_status=CANONICAL_LINK_PENDING,
            source_details_json={
                "review_handling": "flag_review",
                "review_reason_code": REASON_STAGE_NAME_OR_ALIAS,
                "review_message": "Stage name",
            },
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        apply_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            person=person,
            plan=plan,
            people_bucket="needs_review",
            auto_apply_canonicalization=True,
        )
        session.commit()
        session.refresh(person)
        assert person.canonical_link_status == CANONICAL_LINK_PENDING
        assert person.stylebook_person_canonical_id is None
