"""Tests for questionable organization prefilter scoring."""

from __future__ import annotations

import pytest
from backfield_entities.quality.finders._questionable_organization_prefilter import (
    PREFILTER_SCORE_THRESHOLD,
    passes_questionable_organization_prefilter,
    score_questionable_organization_label,
)

_FLAG_LABELS = (
    ("Affordable Care Act", "government", False, False),
    ("Administrative Procedure Act", "government", False, False),
    ("Full Service Community Schools grant", "other", False, False),
    ("Donald Trump", "government", True, False),
    ("Bernie Sanders", "other", True, False),
    ("Grant Park", "other", False, False),
    ("Grammy Awards", "culture_arts", False, False),
    ("Super Bowl", "other", False, False),
    ("World War I", "other", False, False),
    ("Area 5 detectives", "law_enforcement", False, False),
    ("Chicago Bulls coach Billy Donovan", "sports_team", False, False),
)

_KEEP_LABELS = (
    ("Grant Park Advisory Council", "community_group", False, False),
    ("Chicago Department of Law", "government", False, False),
    ("International Olympic Committee", "other", False, False),
    ("Evanston City Council", "legislative_body", False, False),
    ("Recording Academy", "culture_arts", False, False),
)


@pytest.mark.parametrize(
    ("label", "organization_type", "matches_person", "matches_location"),
    _FLAG_LABELS,
)
def test_prefilter_flags_known_bad_organization_labels(
    label: str,
    organization_type: str,
    matches_person: bool,
    matches_location: bool,
) -> None:
    result = score_questionable_organization_label(
        label=label,
        organization_type=organization_type,
        matches_person_label=matches_person,
        matches_location_label=matches_location,
    )
    assert passes_questionable_organization_prefilter(
        result,
        threshold=PREFILTER_SCORE_THRESHOLD,
    ), (label, result.score, result.signals)


@pytest.mark.parametrize(
    ("label", "organization_type", "matches_person", "matches_location"),
    _KEEP_LABELS,
)
def test_prefilter_keeps_known_good_organization_labels(
    label: str,
    organization_type: str,
    matches_person: bool,
    matches_location: bool,
) -> None:
    result = score_questionable_organization_label(
        label=label,
        organization_type=organization_type,
        matches_person_label=matches_person,
        matches_location_label=matches_location,
    )
    assert not passes_questionable_organization_prefilter(
        result,
        threshold=PREFILTER_SCORE_THRESHOLD,
    ), (label, result.score, result.signals)


def test_kenwood_passes_with_location_collision() -> None:
    result = score_questionable_organization_label(
        label="Kenwood",
        organization_type="other",
        matches_location_label=True,
    )
    assert passes_questionable_organization_prefilter(result)
