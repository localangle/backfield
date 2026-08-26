"""Prompt builders for automatic connection classification."""

from __future__ import annotations

from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS,
    auto_link_natures_for_pair,
)
from backfield_entities.connections.types import AutoConnectionCandidatePair


def build_candidate_batch_prompt(
    candidates: tuple[AutoConnectionCandidatePair, ...],
) -> str:
    """Build a prompt whose evidence is explicitly scoped to candidate pairs."""
    blocks: list[str] = []
    for candidate in candidates:
        allowed = sorted(
            auto_link_natures_for_pair(
                candidate.from_entity_type,
                candidate.to_entity_type,
            )
        )
        evidence = "\n".join(f'    - "{snippet}"' for snippet in candidate.evidence.snippets)
        hints = "\n".join(f"    - {hint}" for hint in candidate.evidence.hints)
        blocks.append(
            "\n".join(
                [
                    f"- candidate_id={candidate.candidate_id}",
                    (
                        f"  family: {candidate.from_entity_type} to "
                        f"{candidate.to_entity_type}"
                    ),
                    (
                        f"  from: type={candidate.from_entity_type} "
                        f"id={candidate.from_entity.canonical_id} "
                        f"label={candidate.from_entity.label!r}"
                    ),
                    (
                        f"  to: type={candidate.to_entity_type} "
                        f"id={candidate.to_entity.canonical_id} "
                        f"label={candidate.to_entity.label!r}"
                    ),
                    f"  allowed_natures: {', '.join(allowed) if allowed else '(none)'}",
                    f"  evidence_source: {candidate.evidence.source}",
                    "  article_evidence:",
                    evidence or "    - (none)",
                    "  lower_trust_hints:",
                    hints or "    - (none)",
                ]
            )
        )
    candidate_section = "\n\n".join(blocks)
    return (
        f"prompt_version: {AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS}\n"
        "Judge whether an explicit relationship exists for every candidate pair below.\n\n"
        "Rules:\n"
        "- Return exactly one decision for every candidate_id.\n"
        "- Set link=true only when you would publish the relationship as a fact.\n"
        "- Set link=false when the evidence does not establish a direct relationship, "
        "including uncertainty, co-mention, proximity, shared events, or metadata alone.\n"
        "- The reason must explain and agree with the link judgment.\n"
        "- Article evidence must state or strongly entail a direct relationship.\n"
        "- Lower-trust hints may help interpret article evidence but never prove a relationship.\n"
        "- Do not infer a relationship from co-mention, proximity, shared event, "
        "or metadata alone.\n"
        "- For link=true, copy the supporting quote exactly from that candidate's "
        "article_evidence and use only the submitted endpoints and one allowed nature.\n"
        "- For link=false, use null nature and empty endpoint, description, and quote fields.\n"
        "- Prefer leads over works_for when leadership is explicit.\n"
        "- Athletes on a sports team use plays_for; coaches use coaches.\n"
        "- When a person's affiliation names an organization in the candidate pair, "
        "prefer plays_for or coaches for sports teams and works_for otherwise.\n"
        "- Prose may use a team nickname (e.g. Bears quarterback, Vikings receiver) "
        "while the organization label is the full name; still use plays_for or coaches "
        "when the relationship is explicit.\n"
        "- Journalistic party+district tags after a legislator's name, such as D-Ottawa or "
        "R-Springfield, indicate they represent that place; use represents.\n"
        "- For link=true, confidence must be at least 0.9; prefer link=false when uncertain.\n\n"
        f"Candidates:\n{candidate_section}\n\n"
        'Return JSON only: {"decisions": [{"candidate_id": "candidate-...", '
        '"link": true, "from_entity_id": "...", "to_entity_id": "...", '
        '"description": "...", "nature": "...", "confidence": 0.95, '
        '"quote": "...", "reason": "..."}]}'
    )
