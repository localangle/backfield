"""Worker helpers for Stylebook candidate queue AI review runs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass, replace
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
from backfield_entities.canonical.plan_types import CanonicalPersistPlan
from backfield_entities.catalog.candidate_ai_review import list_open_candidate_ids_for_review
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
from sqlmodel import Session, col, select
from worker.substrate.ai_review_cancel import ai_review_status_is_cancelled, load_review_status
from worker.substrate.canonical.adjudication import (
    LocationAdjudicationPrepared,
    prepare_location_adjudication,
    resolve_location_adjudication_plan,
    run_location_adjudication_llm,
)
from worker.substrate.canonical.parallel_llm import (
    candidate_ai_review_max_concurrent,
    commit_session_before_session_free_llm,
)
from worker.substrate.entities.organization.adjudication import (
    OrganizationAdjudicationPrepared,
    prepare_organization_adjudication,
    resolve_organization_adjudication_plan,
    run_organization_adjudication_llm,
)
from worker.substrate.entities.person.adjudication import (
    PersonAdjudicationPrepared,
    prepare_person_adjudication,
    resolve_person_adjudication_plan,
    run_person_adjudication_llm,
)

logger = logging.getLogger(__name__)

CandidateEntityType = Literal["person", "organization", "location"]


@dataclass(frozen=True)
class _PersonReviewPlan:
    plan: CanonicalPersistPlan
    adjudication_prep: PersonAdjudicationPrepared | None


@dataclass(frozen=True)
class _OrganizationReviewPlan:
    plan: CanonicalPersistPlan
    adjudication_prep: OrganizationAdjudicationPrepared | None


@dataclass(frozen=True)
class _LocationReviewPlan:
    plan: CanonicalPersistPlan
    adjudication_prep: LocationAdjudicationPrepared | None


def _fail_candidate_ai_review(engine: Any, review_id: str, message: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None or ai_review_status_is_cancelled(str(review.status)):
            return
        review.status = "failed"
        review.error_message = message[:10000]
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


def _candidate_ai_review_is_cancelled(engine: Any, review_id: str) -> bool:
    from backfield_db import StylebookCandidateAiReview as ReviewModel

    status = load_review_status(engine, model=ReviewModel, review_id=review_id)
    return ai_review_status_is_cancelled(status)


def _mark_candidate_ai_review_succeeded(engine: Any, review_id: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None or ai_review_status_is_cancelled(str(review.status)):
            return
        review.status = "succeeded"
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


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


def _person_pending_open(session: Session, *, person_id: int, project_id: int) -> bool:
    person = session.get(SubstratePerson, person_id)
    if person is None or int(person.project_id) != project_id:
        return False
    if person.stylebook_person_canonical_id is not None:
        return False
    return str(person.canonical_link_status) == CANONICAL_LINK_PENDING


def _organization_pending_open(
    session: Session, *, organization_id: int, project_id: int
) -> bool:
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != project_id:
        return False
    if organization.stylebook_organization_canonical_id is not None:
        return False
    return str(organization.canonical_link_status) == CANONICAL_LINK_PENDING


def _location_pending_open(session: Session, *, location_id: int, project_id: int) -> bool:
    location = session.get(SubstrateLocation, location_id)
    if location is None or int(location.project_id) != project_id:
        return False
    if location.stylebook_location_canonical_id is not None:
        return False
    return str(location.canonical_link_status) == CANONICAL_LINK_PENDING


def _prepare_person_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: int,
    model: str,
    model_config_id: str | None,
) -> _PersonReviewPlan | None:
    with Session(engine) as session:
        person = session.get(SubstratePerson, person_id)
        if person is None or int(person.project_id) != project_id:
            return None
        if person.stylebook_person_canonical_id is not None:
            return None
        if str(person.canonical_link_status) != CANONICAL_LINK_PENDING:
            return None
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
        adjudication_prep: PersonAdjudicationPrepared | None = None
        if plan_requires_llm_person_canonical_adjudication(plan, person):
            adjudication_prep = prepare_person_adjudication(
                session,
                plan=plan,
                person=person,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
                article_text=article_text,
                mention_texts=mention_texts,
            )
        commit_session_before_session_free_llm(session)
    return _PersonReviewPlan(plan=plan, adjudication_prep=adjudication_prep)


def _apply_person_candidate_review(
    engine: Any,
    *,
    project_id: int,
    person_id: int,
    prepared: _PersonReviewPlan,
) -> bool:
    plan = prepared.plan
    llm_data: dict[str, Any] | None = None
    if prepared.adjudication_prep is not None:
        llm_data = run_person_adjudication_llm(prepared.adjudication_prep)
    with Session(engine) as session:
        if not _person_pending_open(session, person_id=person_id, project_id=project_id):
            return False
        person = session.get(SubstratePerson, person_id)
        if person is None:
            return False
        if prepared.adjudication_prep is not None:
            plan = resolve_person_adjudication_plan(
                plan,
                prepared=replace(prepared.adjudication_prep, person=person),
                llm_data=llm_data,
            )
        has_rec = apply_candidate_ai_review_recommendation(session, person=person, plan=plan)
        session.commit()
        return has_rec


def _process_person_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: int,
    model: str,
    model_config_id: str | None,
) -> bool:
    prepared = _prepare_person_candidate_review(
        engine,
        stylebook_id=stylebook_id,
        project_id=project_id,
        person_id=person_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return False
    return _apply_person_candidate_review(
        engine,
        project_id=project_id,
        person_id=person_id,
        prepared=prepared,
    )


def _prepare_organization_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: int,
    model: str,
    model_config_id: str | None,
) -> _OrganizationReviewPlan | None:
    with Session(engine) as session:
        organization = session.get(SubstrateOrganization, organization_id)
        if organization is None or int(organization.project_id) != project_id:
            return None
        if organization.stylebook_organization_canonical_id is not None:
            return None
        if str(organization.canonical_link_status) != CANONICAL_LINK_PENDING:
            return None
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
        )
        adjudication_prep: OrganizationAdjudicationPrepared | None = None
        if plan_requires_llm_organization_canonical_adjudication(plan, organization):
            adjudication_prep = prepare_organization_adjudication(
                session,
                plan=plan,
                organization=organization,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
            )
        commit_session_before_session_free_llm(session)
    return _OrganizationReviewPlan(plan=plan, adjudication_prep=adjudication_prep)


def _apply_organization_candidate_review(
    engine: Any,
    *,
    project_id: int,
    organization_id: int,
    prepared: _OrganizationReviewPlan,
) -> bool:
    plan = prepared.plan
    llm_data: dict[str, Any] | None = None
    if prepared.adjudication_prep is not None:
        llm_data = run_organization_adjudication_llm(prepared.adjudication_prep)
    with Session(engine) as session:
        if not _organization_pending_open(
            session,
            organization_id=organization_id,
            project_id=project_id,
        ):
            return False
        organization = session.get(SubstrateOrganization, organization_id)
        if organization is None:
            return False
        if prepared.adjudication_prep is not None:
            plan = resolve_organization_adjudication_plan(
                plan,
                prepared=replace(prepared.adjudication_prep, organization=organization),
                llm_data=llm_data,
            )
        has_rec = apply_organization_candidate_ai_review(
            session, organization=organization, plan=plan
        )
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
    prepared = _prepare_organization_candidate_review(
        engine,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=organization_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return False
    return _apply_organization_candidate_review(
        engine,
        project_id=project_id,
        organization_id=organization_id,
        prepared=prepared,
    )


def _location_entry_from_substrate(location: SubstrateLocation) -> dict[str, Any]:
    return {
        "name": location.name,
        "location_type": location.location_type,
        "formatted_address": location.formatted_address,
    }


def _prepare_location_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: int,
    model: str,
    model_config_id: str | None,
) -> _LocationReviewPlan | None:
    with Session(engine) as session:
        location = session.get(SubstrateLocation, location_id)
        if location is None or int(location.project_id) != project_id:
            return None
        if location.stylebook_location_canonical_id is not None:
            return None
        if str(location.canonical_link_status) != CANONICAL_LINK_PENDING:
            return None
        entry = _location_entry_from_substrate(location)
        plan = decide_location_canonical_persist_plan(
            session,
            stylebook_id=stylebook_id,
            places_bucket="ready",
            location=location,
            entry=entry,
        )
        adjudication_prep: LocationAdjudicationPrepared | None = None
        if plan_requires_llm_canonical_adjudication(plan, location):
            adjudication_prep = prepare_location_adjudication(
                session,
                plan=plan,
                location=location,
                stylebook_id=stylebook_id,
                model=model,
                model_config_id=model_config_id,
            )
        commit_session_before_session_free_llm(session)
    return _LocationReviewPlan(plan=plan, adjudication_prep=adjudication_prep)


def _apply_location_candidate_review(
    engine: Any,
    *,
    project_id: int,
    location_id: int,
    prepared: _LocationReviewPlan,
) -> bool:
    plan = prepared.plan
    llm_data: dict[str, Any] | None = None
    if prepared.adjudication_prep is not None:
        llm_data = run_location_adjudication_llm(prepared.adjudication_prep)
    with Session(engine) as session:
        if not _location_pending_open(session, location_id=location_id, project_id=project_id):
            return False
        location = session.get(SubstrateLocation, location_id)
        if location is None:
            return False
        if prepared.adjudication_prep is not None:
            plan = resolve_location_adjudication_plan(
                plan,
                prepared=replace(prepared.adjudication_prep, location=location),
                llm_data=llm_data,
            )
        has_rec = apply_location_candidate_ai_review(session, location=location, plan=plan)
        session.commit()
        return has_rec


def _process_location_candidate_review(
    engine: Any,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: int,
    model: str,
    model_config_id: str | None,
) -> bool:
    prepared = _prepare_location_candidate_review(
        engine,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=location_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return False
    return _apply_location_candidate_review(
        engine,
        project_id=project_id,
        location_id=location_id,
        prepared=prepared,
    )


def _persist_review_progress(
    engine: Any,
    *,
    review_id: str,
    processed_count: int,
    recommendation_count: int,
) -> None:
    if _candidate_ai_review_is_cancelled(engine, review_id):
        return
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None or ai_review_status_is_cancelled(str(review.status)):
            return
        review.processed_count = processed_count
        review.recommendation_count = recommendation_count
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


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
    if _candidate_ai_review_is_cancelled(engine, review_id):
        return
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

    def _run_one_safe(candidate_id: int) -> tuple[int, bool]:
        if _candidate_ai_review_is_cancelled(engine, review_id):
            return candidate_id, False
        try:
            return run_one(candidate_id)
        except Exception:
            logger.exception(
                "candidate AI review failed for %s id=%s",
                entity_type,
                candidate_id,
            )
            return candidate_id, False

    max_workers = candidate_ai_review_max_concurrent()
    recommendation_count = 0
    processed_count = 0

    if max_workers <= 1 or len(candidate_ids) <= 1:
        for candidate_id in candidate_ids:
            if _candidate_ai_review_is_cancelled(engine, review_id):
                return
            _cid, has_rec = _run_one_safe(candidate_id)
            processed_count += 1
            if has_rec:
                recommendation_count += 1
            _persist_review_progress(
                engine,
                review_id=review_id,
                processed_count=processed_count,
                recommendation_count=recommendation_count,
            )
    else:
        workers = min(max_workers, len(candidate_ids))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_id = {
                pool.submit(copy_context().run, _run_one_safe, candidate_id): candidate_id
                for candidate_id in candidate_ids
            }
            for future in as_completed(future_to_id):
                if _candidate_ai_review_is_cancelled(engine, review_id):
                    break
                _cid, has_rec = future.result()
                processed_count += 1
                if has_rec:
                    recommendation_count += 1
                _persist_review_progress(
                    engine,
                    review_id=review_id,
                    processed_count=processed_count,
                    recommendation_count=recommendation_count,
                )

    if not _candidate_ai_review_is_cancelled(engine, review_id):
        _mark_candidate_ai_review_succeeded(engine, review_id)


__all__ = ["list_open_candidate_ids_for_review", "run_candidate_ai_review"]
