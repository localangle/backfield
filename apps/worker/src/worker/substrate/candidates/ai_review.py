"""Worker helpers for Stylebook candidate queue AI review runs."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import (
    StylebookCandidateAiReview,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.entities.location.persist import (
    apply_candidate_ai_review_recommendation as apply_location_candidate_ai_review,
)
from backfield_entities.entities.location.policy import (
    decide_location_canonical_persist_plan,
    plan_requires_llm_canonical_adjudication,
)
from backfield_entities.entities.organization.persist import (
    apply_candidate_ai_review_recommendation as apply_organization_candidate_ai_review,
)
from backfield_entities.entities.organization.policy import (
    decide_organization_canonical_persist_plan,
    plan_requires_llm_organization_canonical_adjudication,
)
from backfield_entities.entities.person.persist import apply_candidate_ai_review_recommendation
from backfield_entities.entities.person.policy import (
    decide_person_canonical_persist_plan,
    plan_requires_llm_person_canonical_adjudication,
)
from sqlalchemy import func
from sqlmodel import Session, col, select
from worker.substrate.canonical.adjudication import (
    prepare_location_adjudication,
    resolve_location_adjudication_plan,
    run_location_adjudication_llm,
)
from worker.substrate.canonical.parallel_llm import canonical_adjudication_max_concurrent
from worker.substrate.entities.organization.adjudication import (
    prepare_organization_adjudication,
    resolve_organization_adjudication_plan,
    run_organization_adjudication_llm,
)
from worker.substrate.entities.person.adjudication import (
    prepare_person_adjudication,
    resolve_person_adjudication_plan,
    run_person_adjudication_llm,
)

CandidateEntityType = Literal["person", "organization", "location"]


def _fail_candidate_ai_review(engine: Any, review_id: str, message: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None:
            return
        review.status = "failed"
        review.error_message = message[:10000]
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


def _mark_candidate_ai_review_succeeded(engine: Any, review_id: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None:
            return
        review.status = "succeeded"
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


def _open_person_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    sort_key = func.coalesce(col(SubstratePerson.sort_key), col(SubstratePerson.normalized_name))
    rows = session.exec(
        select(SubstratePerson.id)
        .where(
            SubstratePerson.project_id == project_id,
            col(SubstratePerson.stylebook_person_canonical_id).is_(None),
            SubstratePerson.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(sort_key)
    ).all()
    return [int(row) for row in rows if row is not None]


def _open_organization_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    rows = session.exec(
        select(SubstrateOrganization.id)
        .where(
            SubstrateOrganization.project_id == project_id,
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
            SubstrateOrganization.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(col(SubstrateOrganization.normalized_name))
    ).all()
    return [int(row) for row in rows if row is not None]


def _open_location_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    rows = session.exec(
        select(SubstrateLocation.id)
        .where(
            SubstrateLocation.project_id == project_id,
            col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(col(SubstrateLocation.normalized_name))
    ).all()
    return [int(row) for row in rows if row is not None]


def _article_context_for_person(
    session: Session,
    *,
    person_id: int,
    project_id: int,
) -> tuple[str | None, list[str]]:
    pair = session.exec(
        select(SubstratePersonMention, SubstrateArticle)
        .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
        .where(
            SubstratePersonMention.person_id == person_id,
            SubstratePersonMention.deleted == False,  # noqa: E712
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
        .order_by(col(SubstratePersonMention.updated_at).desc())
        .limit(1)
    ).first()
    if pair is None:
        return None, []
    mention, article = pair
    article_text = (article.text or "").strip() or None
    mention_texts: list[str] = []
    if mention.id is not None:
        occ = session.exec(
            select(SubstratePersonMentionOccurrence)
            .where(SubstratePersonMentionOccurrence.person_mention_id == int(mention.id))
            .order_by(col(SubstratePersonMentionOccurrence.id))
            .limit(1)
        ).first()
        if occ is not None:
            txt = (occ.quote_text or occ.mention_text or "").strip()
            if txt:
                mention_texts.append(txt)
    if not mention_texts:
        person = session.get(SubstratePerson, person_id)
        if person is not None and person.name:
            mention_texts.append(str(person.name).strip())
    return article_text, mention_texts


def _process_person_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: int,
    model: str,
    model_config_id: str | None,
) -> bool:
    with Session(engine) as session:
        person = session.get(SubstratePerson, person_id)
        if person is None or int(person.project_id) != project_id:
            return False
        if person.stylebook_person_canonical_id is not None:
            return False
        if str(person.canonical_link_status) != CANONICAL_LINK_PENDING:
            return False
        article_text, mention_texts = _article_context_for_person(
            session,
            person_id=person_id,
            project_id=project_id,
        )
        plan = decide_person_canonical_persist_plan(
            session,
            stylebook_id=stylebook_id,
            person=person,
        )
        if plan_requires_llm_person_canonical_adjudication(plan, person):
            prep = prepare_person_adjudication(
                session,
                plan=plan,
                person=person,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
                article_text=article_text,
                mention_texts=mention_texts,
            )
            if prep is not None:
                llm_data = run_person_adjudication_llm(prep)
                plan = resolve_person_adjudication_plan(plan, prepared=prep, llm_data=llm_data)
        has_rec = apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        return has_rec


def _process_organization_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: int,
    model: str,
    model_config_id: str | None,
) -> bool:
    with Session(engine) as session:
        organization = session.get(SubstrateOrganization, organization_id)
        if organization is None or int(organization.project_id) != project_id:
            return False
        if organization.stylebook_organization_canonical_id is not None:
            return False
        if str(organization.canonical_link_status) != CANONICAL_LINK_PENDING:
            return False
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
        )
        if plan_requires_llm_organization_canonical_adjudication(plan, organization):
            prep = prepare_organization_adjudication(
                session,
                plan=plan,
                organization=organization,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
            )
            if prep is not None:
                llm_data = run_organization_adjudication_llm(prep)
                plan = resolve_organization_adjudication_plan(
                    plan, prepared=prep, llm_data=llm_data
                )
        has_rec = apply_organization_candidate_ai_review(
            session, organization=organization, plan=plan
        )
        session.commit()
        return has_rec


def _location_entry_from_substrate(location: SubstrateLocation) -> dict[str, Any]:
    return {
        "name": location.name,
        "location_type": location.location_type,
        "formatted_address": location.formatted_address,
    }


def _process_location_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: int,
    model: str,
    model_config_id: str | None,
) -> bool:
    with Session(engine) as session:
        location = session.get(SubstrateLocation, location_id)
        if location is None or int(location.project_id) != project_id:
            return False
        if location.stylebook_location_canonical_id is not None:
            return False
        if str(location.canonical_link_status) != CANONICAL_LINK_PENDING:
            return False
        entry = _location_entry_from_substrate(location)
        plan = decide_location_canonical_persist_plan(
            session,
            stylebook_id=stylebook_id,
            places_bucket="ready",
            location=location,
            entry=entry,
        )
        if plan_requires_llm_canonical_adjudication(plan, location):
            prep = prepare_location_adjudication(
                session,
                plan=plan,
                location=location,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
            )
            if prep is not None:
                llm_data = run_location_adjudication_llm(prep)
                plan = resolve_location_adjudication_plan(plan, prepared=prep, llm_data=llm_data)
        has_rec = apply_location_candidate_ai_review(session, location=location, plan=plan)
        session.commit()
        return has_rec


def run_candidate_ai_review(
    engine: Any,
    *,
    review_id: str,
    entity_type: CandidateEntityType,
    stylebook_id: int,
    project_id: int,
    candidate_ids: list[int],
    model: str,
    model_config_id: str | None,
) -> None:
    if not candidate_ids:
        _mark_candidate_ai_review_succeeded(engine, review_id)
        return

    processors: dict[CandidateEntityType, Callable[[int], tuple[int, bool]]] = {
        "person": lambda cid: (
            cid,
            _process_person_candidate_review(
                engine,
                stylebook_id=stylebook_id,
                project_id=project_id,
                person_id=cid,
                model=model,
                model_config_id=model_config_id,
            ),
        ),
        "organization": lambda cid: (
            cid,
            _process_organization_candidate_review(
                engine,
                stylebook_id=stylebook_id,
                project_id=project_id,
                organization_id=cid,
                model=model,
                model_config_id=model_config_id,
            ),
        ),
        "location": lambda cid: (
            cid,
            _process_location_candidate_review(
                engine,
                stylebook_id=stylebook_id,
                project_id=project_id,
                location_id=cid,
                model=model,
                model_config_id=model_config_id,
            ),
        ),
    }
    run_one = processors.get(entity_type)
    if run_one is None:
        raise ValueError(f"Unsupported candidate AI review entity_type: {entity_type}")

    max_workers = canonical_adjudication_max_concurrent()
    recommendation_count = 0
    processed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(copy_context().run, lambda cid=cid: run_one(cid)) for cid in candidate_ids
        ]
        for future in as_completed(futures):
            _cid, has_rec = future.result()
            processed += 1
            if has_rec:
                recommendation_count += 1
            with Session(engine) as session:
                review = session.get(StylebookCandidateAiReview, review_id)
                if review is None:
                    continue
                review.processed_count = processed
                review.recommendation_count = recommendation_count
                review.updated_at = datetime.now(UTC)
                session.add(review)
                session.commit()

    _mark_candidate_ai_review_succeeded(engine, review_id)


def list_open_candidate_ids_for_review(
    session: Session,
    *,
    entity_type: CandidateEntityType,
    project_id: int,
) -> list[int]:
    if entity_type == "person":
        return _open_person_candidate_ids(session, project_id=project_id)
    if entity_type == "organization":
        return _open_organization_candidate_ids(session, project_id=project_id)
    if entity_type == "location":
        return _open_location_candidate_ids(session, project_id=project_id)
    raise ValueError(f"Unsupported candidate AI review entity_type: {entity_type}")
