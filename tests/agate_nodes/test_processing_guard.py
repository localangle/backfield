"""Tests for Processing Guard measurements and criteria."""

from __future__ import annotations

import pytest
from agate_nodes.processing_guard.criteria import (
    EstimatedEntityReferencesCriterion,
    ProcessingGuardParams,
    WordCountCriterion,
    evaluate_criteria,
)
from agate_nodes.processing_guard.measure import (
    DETECTOR_VERSION,
    count_words,
    estimate_entity_references,
)
from agate_nodes.processing_guard.node import run_processing_guard

SPORTS_LIST = """
Here is a running list of the top individual performances.

99 yards — Jalen Dupree, Penn Manor vs. Solanco, Week 3
99 yards — Lucas Kreider, Governor Mifflin vs. Wilson, Week 1
97 yards — William Johns, Schuylkill Valley vs. Columbia, Week 4
93 yards — Kam’Rai Nichols, Columbia vs. Kutztown, Week 6
"""


def test_word_count_ignores_digits_and_counts_unicode_names() -> None:
    assert count_words("99 yards — Kam’Rai Nichols") == 3
    assert count_words("") == 0


def test_entity_estimate_counts_repeated_name_spans() -> None:
    observed = estimate_entity_references(SPORTS_LIST)
    # Four players plus two schools on each line. "Week" is not a name.
    assert observed == 12


def test_entity_estimate_joins_name_particles() -> None:
    assert estimate_entity_references("Ludwig van Beethoven played.") == 1


def test_empty_criteria_continue() -> None:
    summary = evaluate_criteria([], text="Jane Doe went home.")
    assert summary.disposition == "continue"
    assert summary.triggered is False
    assert summary.criteria == []


def test_word_count_boundaries_are_exclusive() -> None:
    text = "one two three"
    longer = evaluate_criteria(
        [WordCountCriterion(id="max", type="word_count", operator="greater_than", threshold=3)],
        text=text,
    )
    shorter = evaluate_criteria(
        [WordCountCriterion(id="min", type="word_count", operator="less_than", threshold=3)],
        text=text,
    )
    assert longer.triggered is False
    assert shorter.triggered is False


def test_multiple_findings_can_trigger_together() -> None:
    summary = evaluate_criteria(
        [
            WordCountCriterion(
                id="min-words",
                type="word_count",
                operator="less_than",
                threshold=1000,
            ),
            EstimatedEntityReferencesCriterion(
                id="names",
                type="estimated_entity_references",
                threshold=2,
            ),
        ],
        text=SPORTS_LIST,
    )
    assert summary.disposition == "needs_attention"
    assert summary.detector_version == DETECTOR_VERSION
    assert [finding.criterion_id for finding in summary.criteria if finding.triggered] == [
        "min-words",
        "names",
    ]
    name_finding = summary.criteria[1]
    assert name_finding.estimation is True
    assert name_finding.observed == 12
    assert name_finding.message == (
        "The Processing Guard stopped the processing of this item, based on the "
        "settings established on the node."
    )


def test_duplicate_limit_types_rejected() -> None:
    with pytest.raises(ValueError, match="each limit type only once"):
        ProcessingGuardParams.model_validate(
            {
                "criteria": [
                    {
                        "id": "max-words",
                        "type": "word_count",
                        "operator": "greater_than",
                        "threshold": 1,
                    },
                    {
                        "id": "min-words",
                        "type": "word_count",
                        "operator": "less_than",
                        "threshold": 1,
                    },
                ]
            }
        )


def test_duplicate_criterion_ids_rejected() -> None:
    with pytest.raises(ValueError, match="unique ids"):
        ProcessingGuardParams.model_validate(
            {
                "criteria": [
                    {
                        "id": "same",
                        "type": "word_count",
                        "operator": "greater_than",
                        "threshold": 1,
                    },
                    {"id": "same", "type": "estimated_entity_references", "threshold": 1},
                ]
            }
        )


def test_runner_passes_text_and_summary() -> None:
    out = run_processing_guard(
        {
            "criteria": [
                {"id": "names", "type": "estimated_entity_references", "threshold": 100},
            ]
        },
        {"node-1": {"text": "Jane Doe spoke.", "headline": "Hello"}},
    )
    assert out["text"] == "Jane Doe spoke."
    assert out["headline"] == "Hello"
    assert out["processing_guard"]["disposition"] == "continue"
    assert out["processing_guard"]["criteria"][0]["observed"] == 1


def test_runner_requires_body_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        run_processing_guard({"criteria": []}, {"headline": "No body"})
