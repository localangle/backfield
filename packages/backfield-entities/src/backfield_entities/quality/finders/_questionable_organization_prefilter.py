"""Deterministic prefilter for questionable organization canonicals."""

from __future__ import annotations

import re
from dataclasses import dataclass

PREFILTER_SCORE_THRESHOLD: int = 4

_HARD_LAW_RE = re.compile(
    r"\b(Act|Acts|Ordinance|Regulation|Executive Order|Tax Credit|Voucher)\b"
)
_LOWER_PROGRAM_RE = re.compile(
    r"\b(bill|grant|program|policy|rule|fund|plan|initiative|survey|census)\b",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(
    r"\b(Awards?|Grammys?|Super Bowl|World War|Olympics?|concert|Concert|"
    r"festival|Festival|parade|Parade|Tournament|Championship|Summit|Gala|"
    r"Expo|Games?|Series)\b"
)
_GENERIC_GROUP_RE = re.compile(
    r"\b(officials|residents|witnesses|detectives|prosecutors|coaches|"
    r"students|voters|fans|parents|workers|employees|children|Detectives|"
    r"civil society|grand jury|families)\b",
    re.IGNORECASE,
)
_BROAD_DESCRIPTOR_RE = re.compile(
    r"\b(American|Arizona|National|Local|Regional|State|City|County)\s+"
    r"(civil society|families|grand jury|residents|voters|workers|community)\b",
    re.IGNORECASE,
)
_PUBLICATION_SURVEY_RE = re.compile(
    r"\b(Community Survey|Statistical Abstract|Yearbook|Almanac)\b",
    re.IGNORECASE,
)
_LANDMARK_SITE_RE = re.compile(
    r"\b(Arc de Triomphe|Frank House|Triomphe|Monument|Memorial)\b",
    re.IGNORECASE,
)
_PERSON_NAME_LIKE_RE = re.compile(
    r"^[A-Z][\w'.-]+(?: [A-Z][\w'.áéíóúñ-]+){1,3}$"
)
_INSTITUTION_LABEL_RE = re.compile(
    r"\b(Guitars?|Steel|Elementary|School|Schools|University|College|Capital|"
    r"Industries|Corp|Corporation|Inc|LLC|Fund|Foundation|Academy|Institute|"
    r"Hospital|Church|Bank|Women|Brothers|Sisters|Group|Partners|Assets?|"
    r"Management|Investment|District|Properties|Motors|Energy|Media)\b",
    re.IGNORECASE,
)
_INSTITUTIONAL_ORG_TYPES: frozenset[str] = frozenset(
    {
        "company",
        "local_business",
        "financial_institution",
        "real_estate",
        "nonprofit",
        "community_group",
        "school",
        "school_district",
        "university",
        "hospital",
        "public_health",
        "public_services",
        "utilities",
        "religious_org",
        "culture_arts",
        "sports_team",
        "sports_league",
        "media",
    }
)
_PERSON_ROLE_RE = re.compile(
    r"\b(President|president|Senator|senator|Sen\.?|Governor|governor|Mayor|"
    r"mayor|Judge|judge|coach|Coach|player|rapper|singer|actor|actress|"
    r"billionaire|father|mother|brother|sister)\b"
)
_PLACE_RE = re.compile(
    r"\b(Park|park|Neighborhood|neighborhood|Downtown|downtown|Lakefront|"
    r"lakefront|Beach|beach|River|river|Landmark|landmark|Plaza|plaza|"
    r"Area|area|Region|region|City|city|Town|town|Village|village)\b"
)
_ORG_ANCHOR_RE = re.compile(
    r"\b(Department|department|Office|office|Council|council|Board|board|"
    r"Commission|commission|Authority|authority|Agency|agency|Association|"
    r"association|Foundation|foundation|Company|company|Inc|LLC|School|"
    r"school|University|university|Hospital|hospital|Church|church|Union|"
    r"union|League|league|Team|team|Club|club|Committee|committee|"
    r"Academy|academy|District|district|Center|center|Centre|centre|"
    r"Institute|institute|Corporation|corporation|Corp|College|college|"
    r"Police|police|Sheriff|sheriff|Bureau|bureau|Coalition|coalition|"
    r"Alliance|alliance|Federation|federation|Museum|museum|Theatre|theatre|"
    r"Theater|theater|Forum|forum)\b"
)


@dataclass(frozen=True)
class QuestionableOrganizationPrefilterResult:
    score: int
    signals: tuple[str, ...]
    matches_person_label: bool
    matches_location_label: bool
    has_org_anchor: bool


def score_questionable_organization_label(
    *,
    label: str,
    organization_type: str | None,
    matches_person_label: bool = False,
    matches_location_label: bool = False,
) -> QuestionableOrganizationPrefilterResult:
    """Return a prefilter score and signal tags for one organization label."""
    clean_label = (label or "").strip()
    typ = (organization_type or "").strip().lower()
    has_anchor = bool(_ORG_ANCHOR_RE.search(clean_label))
    signals: list[str] = []
    score = 0

    law = bool(_HARD_LAW_RE.search(clean_label) or _LOWER_PROGRAM_RE.search(clean_label))
    event = bool(_EVENT_RE.search(clean_label))
    generic = bool(
        _GENERIC_GROUP_RE.search(clean_label) or _BROAD_DESCRIPTOR_RE.search(clean_label)
    )
    publication = bool(_PUBLICATION_SURVEY_RE.search(clean_label))
    landmark = bool(_LANDMARK_SITE_RE.search(clean_label))
    person_name_like = bool(
        _PERSON_NAME_LIKE_RE.match(clean_label)
        and not has_anchor
        and not law
        and not publication
        and typ not in _INSTITUTIONAL_ORG_TYPES
        and not _INSTITUTION_LABEL_RE.search(clean_label)
    )
    role = bool(_PERSON_ROLE_RE.search(clean_label))
    place = bool(_PLACE_RE.search(clean_label))

    if matches_person_label:
        score += 4
        signals.append("cross_catalog_person")
    if matches_location_label:
        score += 4
        signals.append("cross_catalog_location")
    if law:
        score += 3
        signals.append("law_policy_program")
    if event:
        score += 3
        signals.append("event_award_competition_history")
    if generic:
        score += 3
        signals.append("generic_role_group")
    if "," in clean_label and not has_anchor:
        score += 3
        signals.append("creative_work_title")
    if typ == "culture_arts" and not has_anchor and not publication:
        score += 3
        signals.append("culture_arts_without_org_anchor")
    if landmark:
        score += 3
        signals.append("landmark_or_site")
    if person_name_like:
        score += 3
        signals.append("person_name_like")
    if role and not has_anchor:
        score += 3
        signals.append("person_role_phrase_no_anchor")
    elif role and matches_person_label:
        score += 2
        signals.append("person_role_with_person_collision")
    if place and not has_anchor:
        score += 3
        signals.append("place_like_without_org_anchor")

    gov_other_type_mismatch = typ in {"government", "other"} and (
        law or (event and not has_anchor) or (role and matches_person_label)
    )
    type_mismatch = (
        gov_other_type_mismatch
        or (typ in {"culture_arts", "sports_league"} and event and not has_anchor)
        or (typ in {"public_services", "government", "other"} and place and not has_anchor)
    )
    if type_mismatch:
        score += 2
        signals.append("type_surface_mismatch")
    if not has_anchor:
        score += 1
        signals.append("no_org_anchor")
    else:
        score -= 3

    return QuestionableOrganizationPrefilterResult(
        score=score,
        signals=tuple(signals),
        matches_person_label=matches_person_label,
        matches_location_label=matches_location_label,
        has_org_anchor=has_anchor,
    )


def passes_questionable_organization_prefilter(
    result: QuestionableOrganizationPrefilterResult,
    *,
    threshold: int = PREFILTER_SCORE_THRESHOLD,
) -> bool:
    return result.score >= threshold
