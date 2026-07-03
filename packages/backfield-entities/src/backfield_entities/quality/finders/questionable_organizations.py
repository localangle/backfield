"""Find organization canonicals that may not be real organizations."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlmodel import Session, select

from backfield_entities.quality.dismissals import canonical_dismissal_key, load_dismissed_keys
from backfield_entities.quality.finders._questionable_organization_evidence import (
    linked_substrate_counts_for_organization_canonicals,
    mention_counts_for_organization_canonicals,
    organization_project_ids,
    sample_mention_texts_for_organization_canonicals,
)
from backfield_entities.quality.finders._questionable_organization_prefilter import (
    PREFILTER_SCORE_THRESHOLD,
    passes_questionable_organization_prefilter,
    score_questionable_organization_label,
)
from backfield_entities.quality.llm_questionable_organizations import (
    DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE,
    DEFAULT_QUESTIONABLE_ORG_LLM_MODEL,
    QuestionableOrganizationCandidate,
    QuestionableOrganizationReviewResult,
    review_questionable_organization_batches,
    should_persist_questionable_organization_review,
)

if TYPE_CHECKING:
    from backfield_entities.quality.check_runs import CleanupCheckItem, CleanupRunScope

_CHECK_ID = "questionable-organization-canonicals"


def _load_label_collision_sets(
    session: Session,
    *,
    stylebook_id: int,
) -> tuple[set[str], set[str]]:
    person_labels = {
        str(row).lower()
        for row in session.exec(
            select(StylebookPersonCanonical.label).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id,
                StylebookPersonCanonical.status == "active",
            )
        ).all()
        if row
    }
    location_labels = {
        str(row).lower()
        for row in session.exec(
            select(StylebookLocationCanonical.label).where(
                StylebookLocationCanonical.stylebook_id == stylebook_id,
                StylebookLocationCanonical.status == "active",
            )
        ).all()
        if row
    }
    return person_labels, location_labels


def prefilter_questionable_organization_canonicals(
    session: Session,
    *,
    stylebook_id: int,
    threshold: int = PREFILTER_SCORE_THRESHOLD,
) -> list[tuple[StylebookOrganizationCanonical, int, tuple[str, ...]]]:
    person_labels, location_labels = _load_label_collision_sets(
        session,
        stylebook_id=stylebook_id,
    )
    rows = session.exec(
        select(StylebookOrganizationCanonical).where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            StylebookOrganizationCanonical.status == "active",
        )
    ).all()
    candidates: list[tuple[StylebookOrganizationCanonical, int, tuple[str, ...]]] = []
    for row in rows:
        if row.id is None or not row.label:
            continue
        label_key = str(row.label).strip().lower()
        scored = score_questionable_organization_label(
            label=str(row.label),
            organization_type=row.organization_type,
            matches_person_label=label_key in person_labels,
            matches_location_label=label_key in location_labels,
        )
        if not passes_questionable_organization_prefilter(scored, threshold=threshold):
            continue
        candidates.append((row, scored.score, scored.signals))
    candidates.sort(key=lambda item: (-item[1], str(item[0].label or "").lower()))
    return candidates


def count_questionable_organization_canonicals(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    """Materialized check: hub/detail counts come from the latest successful run."""
    _ = (session, stylebook_id, organization_id)
    return 0


def build_questionable_organization_check_items(
    session: Session,
    *,
    scope: CleanupRunScope,
    call_llm: Callable[..., str],
    model: str = DEFAULT_QUESTIONABLE_ORG_LLM_MODEL,
    model_config_id: str | None = None,
    batch_size: int = DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE,
    threshold: int = PREFILTER_SCORE_THRESHOLD,
) -> list[CleanupCheckItem]:
    stylebook_id = scope.stylebook_id
    project_ids = (
        list(scope.project_ids)
        if scope.project_ids is not None
        else organization_project_ids(session, organization_id=scope.organization_id)
    )

    prefiltered = prefilter_questionable_organization_canonicals(
        session,
        stylebook_id=stylebook_id,
        threshold=threshold,
    )
    if not prefiltered:
        return []

    canonical_ids = [str(row.id) for row, _score, _signals in prefiltered if row.id is not None]
    mention_counts = mention_counts_for_organization_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )
    linked_counts = linked_substrate_counts_for_organization_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )
    sample_mentions = sample_mention_texts_for_organization_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )

    llm_candidates = [
        QuestionableOrganizationCandidate(
            canonical_id=str(row.id),
            label=str(row.label),
            slug=str(row.slug),
            organization_type=row.organization_type,
            prefilter_score=score,
            prefilter_signals=signals,
            linked_count=linked_counts.get(str(row.id), 0),
            mention_count=mention_counts.get(str(row.id), 0),
            sample_mentions=sample_mentions.get(str(row.id), ()),
        )
        for row, score, signals in prefiltered
        if row.id is not None
    ]
    reviews = review_questionable_organization_batches(
        llm_candidates,
        call_llm=call_llm,
        model=model,
        model_config_id=model_config_id,
        batch_size=batch_size,
    )
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=_CHECK_ID,
    )
    return _items_from_reviews(
        prefiltered=prefiltered,
        reviews=reviews,
        mention_counts=mention_counts,
        linked_counts=linked_counts,
        sample_mentions=sample_mentions,
        dismissed=dismissed,
    )


def _items_from_reviews(
    *,
    prefiltered: list[tuple[StylebookOrganizationCanonical, int, tuple[str, ...]]],
    reviews: dict[str, QuestionableOrganizationReviewResult],
    mention_counts: dict[str, int],
    linked_counts: dict[str, int],
    sample_mentions: dict[str, tuple[str, ...]],
    dismissed: set[str],
) -> list[CleanupCheckItem]:
    from backfield_entities.quality.check_runs import CleanupCheckItem

    items: list[CleanupCheckItem] = []
    for row, score, signals in prefiltered:
        if row.id is None:
            continue
        canonical_id = str(row.id)
        if canonical_id in dismissed:
            continue
        review = reviews.get(canonical_id)
        if review is None or not should_persist_questionable_organization_review(review):
            continue
        label = str(row.label)
        mentions = list(sample_mentions.get(canonical_id, ()))
        payload = {
            "organization_type": row.organization_type,
            "prefilter_score": score,
            "prefilter_signals": list(signals),
            "llm_decision": review.decision,
            "category": review.category,
            "confidence": review.confidence,
            "explanation": review.explanation,
            "suggested_entity_type": review.suggested_entity_type,
            "sample_mentions": mentions,
            "linked_count": int(linked_counts.get(canonical_id, 0)),
            "mention_count": int(mention_counts.get(canonical_id, 0)),
        }
        searchable_parts = [
            label,
            review.explanation,
            review.category,
            review.suggested_entity_type,
            *signals,
            *mentions,
        ]
        items.append(
            CleanupCheckItem(
                item_kind="list",
                item_key=canonical_id,
                label=label,
                canonical_ids=[canonical_id],
                pair_keys=[canonical_dismissal_key(canonical_id)],
                payload=payload,
                searchable_text=" ".join(
                    part.strip().lower() for part in searchable_parts if part and str(part).strip()
                ),
            )
        )
    return items
