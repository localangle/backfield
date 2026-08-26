"""Currentness-only LLM review for resolved dynamic connection proposals."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass, field
from datetime import datetime

from backfield_entities.connections.caps import MAX_CONNECTION_REQUEST_CONCURRENCY
from backfield_entities.connections.types import (
    AutoConnectionEdgeProposal,
    ResolvedEdgeCurrentnessDecision,
)

logger = logging.getLogger(__name__)

CURRENTNESS_REVIEW_BATCH_SIZE = 16
CURRENTNESS_REVIEW_PROMPT_VERSION = "connection_currentness_v1"


@dataclass(frozen=True)
class ResolvedEdgeCurrentnessReviewItem:
    review_id: str
    edge: AutoConnectionEdgeProposal
    from_entity_type: str
    to_entity_type: str


@dataclass
class CurrentnessReviewCounts:
    attempted: int = 0
    reviewed: int = 0
    current: int = 0
    former: int = 0
    unspecified: int = 0
    requests: int = 0
    failed_requests: int = 0
    malformed_decisions: int = 0
    missing_decisions: int = 0


@dataclass(frozen=True)
class CurrentnessReviewResult:
    edges_by_review_id: dict[str, AutoConnectionEdgeProposal]
    counts: CurrentnessReviewCounts = field(default_factory=CurrentnessReviewCounts)


def _chunks(
    items: tuple[ResolvedEdgeCurrentnessReviewItem, ...],
) -> tuple[tuple[ResolvedEdgeCurrentnessReviewItem, ...], ...]:
    return tuple(
        items[index : index + CURRENTNESS_REVIEW_BATCH_SIZE]
        for index in range(0, len(items), CURRENTNESS_REVIEW_BATCH_SIZE)
    )


def _prompt(
    items: tuple[ResolvedEdgeCurrentnessReviewItem, ...],
    *,
    reference_at: datetime,
) -> str:
    payload = [
        {
            "review_id": item.review_id,
            "from_entity_type": item.from_entity_type,
            "to_entity_type": item.to_entity_type,
            "nature": item.edge.nature,
            "description": item.edge.description,
            "quote": item.edge.quote,
        }
        for item in items
    ]
    return (
        f"prompt_version: {CURRENTNESS_REVIEW_PROMPT_VERSION}\n"
        f"Article reference time: {reference_at.isoformat()}\n"
        "Classify the reported currentness of every resolved dynamic relationship.\n"
        "- Use current only when the quote presents the relationship as ongoing at the "
        "article reference time.\n"
        "- Use former only when the quote explicitly presents the relationship as ended "
        "or historical.\n"
        "- Use unspecified when the wording is ambiguous.\n"
        "- Do not infer former status from article age alone.\n"
        "- Return exactly one decision for every review_id.\n\n"
        f"Relationships:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return JSON only: "
        '{"decisions":[{"review_id":"...",'
        '"asserted_currentness":"current|former|unspecified",'
        '"reason":"brief explanation"}]}'
    )


def review_resolved_edge_currentness(
    *,
    items: tuple[ResolvedEdgeCurrentnessReviewItem, ...],
    reference_at: datetime,
    model: str,
    model_config_id: str | None,
    call_llm: Callable[..., str],
) -> CurrentnessReviewResult:
    """Review all supplied edges; failed or missing decisions remain unreviewed."""
    counts = CurrentnessReviewCounts(attempted=len(items))
    if not items:
        return CurrentnessReviewResult(edges_by_review_id={}, counts=counts)

    batches = _chunks(items)
    prompts = tuple((batch, _prompt(batch, reference_at=reference_at)) for batch in batches)
    counts.requests = len(prompts)

    def _call(prompt: str) -> str:
        return call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            model_config_id=model_config_id,
        )

    responses: dict[int, str | None] = {}
    with ThreadPoolExecutor(
        max_workers=max(
            1,
            min(MAX_CONNECTION_REQUEST_CONCURRENCY, len(prompts)),
        )
    ) as executor:
        futures = {
            executor.submit(copy_context().run, _call, prompt): index
            for index, (_batch, prompt) in enumerate(prompts)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                responses[index] = future.result()
            except Exception as exc:
                logger.warning("Resolved-edge currentness review failed: %s", exc)
                responses[index] = None
                counts.failed_requests += 1

    reviewed_edges: dict[str, AutoConnectionEdgeProposal] = {}
    for index, (batch, _prompt_text) in enumerate(prompts):
        raw = responses.get(index)
        if raw is None:
            counts.missing_decisions += len(batch)
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            counts.malformed_decisions += len(batch)
            continue
        rows = payload.get("decisions") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            counts.malformed_decisions += len(batch)
            continue

        items_by_id = {item.review_id: item for item in batch}
        decided_ids: set[str] = set()
        for row in rows:
            try:
                decision = ResolvedEdgeCurrentnessDecision.model_validate(row)
            except Exception:
                counts.malformed_decisions += 1
                continue
            item = items_by_id.get(decision.review_id)
            if item is None or decision.review_id in decided_ids:
                counts.malformed_decisions += 1
                continue
            decided_ids.add(decision.review_id)
            reviewed_edges[decision.review_id] = item.edge.model_copy(
                update={
                    "asserted_currentness": decision.asserted_currentness,
                    "currentness_review_source": "llm",
                }
            )
            counts.reviewed += 1
            if decision.asserted_currentness == "current":
                counts.current += 1
            elif decision.asserted_currentness == "former":
                counts.former += 1
            else:
                counts.unspecified += 1
        counts.missing_decisions += len(items_by_id.keys() - decided_ids)

    return CurrentnessReviewResult(
        edges_by_review_id=reviewed_edges,
        counts=counts,
    )
