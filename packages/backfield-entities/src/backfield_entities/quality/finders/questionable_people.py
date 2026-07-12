"""Find person canonicals that may not be real people."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backfield_db import (
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from sqlmodel import Session, col, func, select

from backfield_entities.quality.dismissals import canonical_dismissal_key, load_dismissed_keys
from backfield_entities.quality.finders._questionable_organization_evidence import (
    organization_project_ids,
)

if TYPE_CHECKING:
    from backfield_entities.quality.check_runs import CleanupCheckItem, CleanupRunScope

logger = logging.getLogger(__name__)

_CHECK_ID = "questionable-person-canonicals"
PREFILTER_SCORE_THRESHOLD = 4
MAX_SAMPLE_MENTIONS = 3
_MAX_MENTION_TEXT_LEN = 220

_ALL_CAPS_RE = re.compile(r"^[A-Z0-9&.-]{2,}$")
_ASSOCIATION_RE = re.compile(
    r"\b(Association|Federation|Coalition|Commission|Committee|Council|Board|"
    r"Alliance|Union|Party)\b",
    re.IGNORECASE,
)
_COMPANY_RE = re.compile(
    r"\b(Company|Corp|Corporation|Inc|LLC|Ltd|Partners|Capital|Group|Holdings|"
    r"Industries|Technologies|Systems|Associates|Bank|Credit|Management|Assets?)\b",
    re.IGNORECASE,
)
_SCHOOL_RE = re.compile(
    r"\b(School|Schools|Academy|Elementary|High School|College|University|District)\b",
    re.IGNORECASE,
)
_HEALTH_RE = re.compile(
    r"\b(Hospital|Medical Center|Health|Clinic|Disease Control|Public Health|Red Cross)\b",
    re.IGNORECASE,
)
_GOVERNMENT_RE = re.compile(
    r"\b(Police|Sheriff|Department|Office|Bureau|Assembly|Attorney General|"
    r"Administration|Agency|Authority|Task Force)\b",
    re.IGNORECASE,
)
_MEDIA_RE = re.compile(
    r"\b(News|Tribune|Times|Sun-Times|WBEZ|BBC|CBS|WTTW|NPR|Radio|Media|Press)\b",
    re.IGNORECASE,
)
_ROLE_PHRASE_RE = re.compile(
    r"\b(spokesperson|officials?|officers?|authorities|police|staff|medical staff)\b",
    re.IGNORECASE,
)
_INSTITUTIONAL_ORG_TYPES = frozenset(
    {
        "company",
        "local_business",
        "financial_institution",
        "real_estate",
        "nonprofit",
        "community_group",
        "religious_org",
        "school",
        "school_district",
        "university",
        "hospital",
        "public_health",
        "public_services",
        "utilities",
        "law_enforcement",
        "government",
        "legislative_body",
        "political_party",
        "court",
        "media",
        "sports_team",
        "sports_league",
    }
)


@dataclass(frozen=True)
class QuestionablePersonPrefilterResult:
    score: int
    signals: tuple[str, ...]
    category: str
    confidence: str
    explanation: str
    suggested_entity_type: str
    matching_organization_type: str | None = None


def _normalized_key(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _score_questionable_person_label(
    *,
    label: str,
    person_type: str | None,
    matching_organization_type: str | None,
) -> QuestionablePersonPrefilterResult:
    clean_label = str(label or "").strip()
    pt = str(person_type or "").strip().lower()
    org_type = str(matching_organization_type or "").strip().lower() or None
    signals: list[str] = []
    score = 0

    if org_type:
        score += 5
        signals.append("cross_catalog_organization")
        if org_type in _INSTITUTIONAL_ORG_TYPES:
            score += 2
            signals.append("matching_institutional_org_type")
    if _ASSOCIATION_RE.search(clean_label):
        score += 4
        signals.append("association_civic_body")
    if _COMPANY_RE.search(clean_label):
        score += 4
        signals.append("company_financial_institution")
    if _SCHOOL_RE.search(clean_label):
        score += 4
        signals.append("school_university")
    if _HEALTH_RE.search(clean_label):
        score += 4
        signals.append("healthcare_public_health")
    if _GOVERNMENT_RE.search(clean_label):
        score += 4
        signals.append("government_agency_office")
    if _MEDIA_RE.search(clean_label):
        score += 3
        signals.append("media_outlet")
    if _ROLE_PHRASE_RE.search(clean_label):
        score += 3
        signals.append("role_phrase_without_person_name")
    if _ALL_CAPS_RE.match(clean_label):
        score += 2
        signals.append("all_caps_acronym")
    if pt in {
        "government_official",
        "business_owner_executive",
        "business_professional",
        "media_journalism",
        "law_enforcement_public_safety",
        "healthcare_worker",
    } and signals:
        score += 1
        signals.append("person_type_surface_mismatch")

    category = "organization_like"
    suggested = "organization" if org_type or "all_caps_acronym" not in signals else "unknown"
    confidence = "high" if score >= 7 or org_type else "medium"
    explanation = _explanation_for_signals(signals, org_type)
    return QuestionablePersonPrefilterResult(
        score=score,
        signals=tuple(signals),
        category=category,
        confidence=confidence,
        explanation=explanation,
        suggested_entity_type=suggested,
        matching_organization_type=org_type,
    )


def _explanation_for_signals(signals: Iterable[str], org_type: str | None) -> str:
    signal_set = set(signals)
    if "cross_catalog_organization" in signal_set:
        if org_type:
            return f"This label matches an existing {org_type.replace('_', ' ')} organization."
        return "This label matches an existing organization canonical."
    if "role_phrase_without_person_name" in signal_set:
        return "This looks like an unnamed role or staff group, not an individual person."
    if "association_civic_body" in signal_set:
        return "This looks like an association, committee, council, or civic body."
    if "company_financial_institution" in signal_set:
        return "This looks like a company, firm, or financial institution."
    if "school_university" in signal_set:
        return "This looks like a school, university, or district."
    if "healthcare_public_health" in signal_set:
        return "This looks like a hospital or public health institution."
    if "government_agency_office" in signal_set:
        return "This looks like a government agency, office, or department."
    if "media_outlet" in signal_set:
        return "This looks like a media outlet, not an individual person."
    return "This label has institution-like signals and may not be a person."


def _organization_type_by_label(
    session: Session,
    *,
    stylebook_id: int,
) -> dict[str, str | None]:
    rows = session.exec(
        select(
            StylebookOrganizationCanonical.label,
            StylebookOrganizationCanonical.organization_type,
        )
        .where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            StylebookOrganizationCanonical.status == "active",
        )
    ).all()
    out: dict[str, str | None] = {}
    for label, organization_type in rows:
        key = _normalized_key(label)
        if key:
            out[key] = str(organization_type) if organization_type else None
    return out


def _mention_counts_for_person_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _linked_counts_for_person_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePerson.id)),
        )
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _normalize_sample_text(value: str | None) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) > _MAX_MENTION_TEXT_LEN:
        return cleaned[: _MAX_MENTION_TEXT_LEN - 1] + "..."
    return cleaned


def _sample_mentions_for_person_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            SubstratePersonMentionOccurrence.mention_text,
        )
        .select_from(SubstratePersonMentionOccurrence)
        .join(
            SubstratePersonMention,
            SubstratePersonMention.id == SubstratePersonMentionOccurrence.person_mention_id,
        )
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
            SubstratePersonMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(col(SubstratePersonMentionOccurrence.id).desc())
    ).all()
    bucket: dict[str, list[str]] = {}
    for canonical_id, mention_text in rows:
        if canonical_id is None:
            continue
        normalized = _normalize_sample_text(mention_text)
        if not normalized:
            continue
        values = bucket.setdefault(str(canonical_id), [])
        if normalized not in values and len(values) < MAX_SAMPLE_MENTIONS:
            values.append(normalized)
    return {key: tuple(values) for key, values in bucket.items()}


def prefilter_questionable_person_canonicals(
    session: Session,
    *,
    stylebook_id: int,
    threshold: int = PREFILTER_SCORE_THRESHOLD,
) -> list[tuple[StylebookPersonCanonical, QuestionablePersonPrefilterResult]]:
    organization_type_by_label = _organization_type_by_label(session, stylebook_id=stylebook_id)
    rows = session.exec(
        select(StylebookPersonCanonical).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonCanonical.status == "active",
        )
    ).all()
    candidates: list[tuple[StylebookPersonCanonical, QuestionablePersonPrefilterResult]] = []
    for row in rows:
        if row.id is None or not row.label:
            continue
        scored = _score_questionable_person_label(
            label=str(row.label),
            person_type=row.person_type,
            matching_organization_type=organization_type_by_label.get(_normalized_key(row.label)),
        )
        if scored.score < threshold:
            continue
        candidates.append((row, scored))
    candidates.sort(key=lambda item: (-item[1].score, str(item[0].label or "").lower()))
    return candidates


def count_questionable_person_canonicals(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    """Materialized check: hub/detail counts come from the latest successful run."""
    _ = (session, stylebook_id, organization_id)
    return 0


def build_questionable_person_check_items(
    session: Session,
    *,
    scope: CleanupRunScope,
    threshold: int = PREFILTER_SCORE_THRESHOLD,
) -> list[CleanupCheckItem]:
    from backfield_entities.quality.check_runs import CleanupCheckItem

    stylebook_id = scope.stylebook_id
    project_ids = (
        list(scope.project_ids)
        if scope.project_ids is not None
        else organization_project_ids(session, organization_id=scope.organization_id)
    )
    prefiltered = prefilter_questionable_person_canonicals(
        session,
        stylebook_id=stylebook_id,
        threshold=threshold,
    )
    logger.info(
        "Questionable person prefilter: %d candidates passed threshold %d",
        len(prefiltered),
        threshold,
    )
    if not prefiltered:
        return []

    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=_CHECK_ID,
    )
    if dismissed:
        before = len(prefiltered)
        prefiltered = [
            (row, scored)
            for row, scored in prefiltered
            if row.id is not None and str(row.id) not in dismissed
        ]
        logger.info(
            "Questionable person dismissed filter: skipped %d previously kept canonicals",
            before - len(prefiltered),
        )
    if not prefiltered:
        return []

    canonical_ids = [str(row.id) for row, _scored in prefiltered if row.id is not None]
    mention_counts = _mention_counts_for_person_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )
    linked_counts = _linked_counts_for_person_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )
    sample_mentions = _sample_mentions_for_person_canonicals(
        session,
        project_ids=project_ids,
        canonical_ids=canonical_ids,
    )

    items: list[CleanupCheckItem] = []
    for row, scored in prefiltered:
        if row.id is None:
            continue
        canonical_id = str(row.id)
        label = str(row.label)
        mentions = list(sample_mentions.get(canonical_id, ()))
        payload = {
            "person_type": row.person_type,
            "prefilter_score": scored.score,
            "prefilter_signals": list(scored.signals),
            "category": scored.category,
            "confidence": scored.confidence,
            "explanation": scored.explanation,
            "suggested_entity_type": scored.suggested_entity_type,
            "matching_organization_type": scored.matching_organization_type,
            "sample_mentions": mentions,
            "linked_count": int(linked_counts.get(canonical_id, 0)),
            "mention_count": int(mention_counts.get(canonical_id, 0)),
        }
        searchable_parts = [
            label,
            scored.explanation,
            scored.category,
            scored.suggested_entity_type,
            scored.matching_organization_type,
            *(scored.signals),
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
                    str(part).strip().lower()
                    for part in searchable_parts
                    if part and str(part).strip()
                ),
            )
        )
    return items
