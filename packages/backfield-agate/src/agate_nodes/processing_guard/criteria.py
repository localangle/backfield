"""Typed Processing Guard criteria and their evaluation results."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from agate_nodes.processing_guard.measure import (
    DETECTOR_VERSION,
    count_words,
    estimate_entity_references,
)

CriterionOperator = Literal["less_than", "greater_than"]


class WordCountCriterion(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["word_count"]
    operator: CriterionOperator
    threshold: int = Field(ge=0)


class EstimatedEntityReferencesCriterion(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["estimated_entity_references"]
    threshold: int = Field(ge=0)


ProcessingGuardCriterion = Annotated[
    WordCountCriterion | EstimatedEntityReferencesCriterion,
    Field(discriminator="type"),
]


class ProcessingGuardParams(BaseModel):
    criteria: list[ProcessingGuardCriterion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_criteria(self) -> ProcessingGuardParams:
        seen_ids: set[str] = set()
        seen_types: set[str] = set()
        for criterion in self.criteria:
            if criterion.id in seen_ids:
                raise ValueError(
                    "Processing Guard criteria must have unique ids "
                    f"(duplicate {criterion.id!r})."
                )
            if criterion.type in seen_types:
                raise ValueError(
                    "Processing Guard allows each limit type only once "
                    f"(duplicate {criterion.type!r})."
                )
            seen_ids.add(criterion.id)
            seen_types.add(criterion.type)
        return self


class CriterionFinding(BaseModel):
    criterion_id: str
    type: str
    operator: CriterionOperator
    threshold: int
    observed: int
    estimation: bool
    detector_version: str | None = None
    triggered: bool
    message: str


class ProcessingGuardSummary(BaseModel):
    disposition: Literal["continue", "needs_attention"]
    triggered: bool
    detector_version: str
    criteria: list[CriterionFinding] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    #: True only when this attempt continued after a limit was exceeded.
    continued_anyway: bool = False


def _word_count_message(*, operator: CriterionOperator, triggered: bool) -> str:
    if not triggered:
        if operator == "greater_than":
            return "This story is within the maximum length for this flow."
        return "This story is within the minimum length for this flow."
    if operator == "greater_than":
        return "This story is longer than this flow is set to process."
    return "This story is shorter than this flow is set to process."


def _entity_message(*, triggered: bool) -> str:
    if triggered:
        return "This story may contain more entities than this flow is set to process."
    return "The estimated number of entities is within the limit for this flow."


def _triggered(observed: int, operator: CriterionOperator, threshold: int) -> bool:
    if operator == "greater_than":
        return observed > threshold
    return observed < threshold


def evaluate_criteria(
    criteria: list[ProcessingGuardCriterion],
    *,
    text: str,
) -> ProcessingGuardSummary:
    """Evaluate every criterion. An empty list continues processing."""
    word_count = count_words(text)
    entity_references = estimate_entity_references(text)
    findings: list[CriterionFinding] = []
    for criterion in criteria:
        if isinstance(criterion, WordCountCriterion):
            triggered = _triggered(word_count, criterion.operator, criterion.threshold)
            findings.append(
                CriterionFinding(
                    criterion_id=criterion.id,
                    type=criterion.type,
                    operator=criterion.operator,
                    threshold=criterion.threshold,
                    observed=word_count,
                    estimation=False,
                    detector_version=None,
                    triggered=triggered,
                    message=_word_count_message(operator=criterion.operator, triggered=triggered),
                )
            )
            continue
        triggered = entity_references > criterion.threshold
        findings.append(
            CriterionFinding(
                criterion_id=criterion.id,
                type=criterion.type,
                operator="greater_than",
                threshold=criterion.threshold,
                observed=entity_references,
                estimation=True,
                detector_version=DETECTOR_VERSION,
                triggered=triggered,
                message=_entity_message(triggered=triggered),
            )
        )
    messages = [finding.message for finding in findings if finding.triggered]
    needs_attention = bool(messages)
    return ProcessingGuardSummary(
        disposition="needs_attention" if needs_attention else "continue",
        triggered=needs_attention,
        detector_version=DETECTOR_VERSION,
        criteria=findings,
        messages=messages,
    )
