"""Prompt builders for automatic connection classification."""

from __future__ import annotations

from backfield_entities.connections.same_site_hints import SameSiteOrgLocationHint
from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS,
    AUTO_CONNECTION_PROMPT_VERSION_NATURE_CATALOG,
    AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS,
    auto_link_natures_for_pair,
)
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    LinkedEntitySnapshot,
)


def _format_entity_block(entity: LinkedEntitySnapshot) -> str:
    lines = [f"- id={entity.canonical_id} label={entity.label!r}"]
    if entity.location_type:
        lines.append(f"  location_type={entity.location_type!r}")
    if entity.affiliation:
        lines.append(f"  affiliation={entity.affiliation!r}")
    if entity.organization_type:
        lines.append(f"  organization_type={entity.organization_type!r}")
    if entity.snippets:
        preview = " | ".join(entity.snippets[:2])
        lines.append(f"  snippets: {preview}")
    return "\n".join(lines)


def _format_same_site_hints_section(
    hints: tuple[SameSiteOrgLocationHint, ...],
) -> str:
    if not hints:
        return ""
    lines = [
        "Candidate same-site pairs (organization primary name matches place primary name; "
        "confirm or reject each with explicit evidence):"
    ]
    for hint in hints:
        lines.append(
            f"- org id={hint.org.canonical_id} label={hint.org.label!r} ↔ "
            f"location id={hint.location.canonical_id} label={hint.location.label!r} "
            f"(match_basis={hint.match_basis})"
        )
    lines.append(
        "- When confirmed, prefer located_at with a narrative reason grounded in the snippets."
    )
    return "\n".join(lines) + "\n\n"


def build_family_classification_prompt(
    *,
    from_type: str,
    to_type: str,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    pair_snippets: tuple[str, ...],
    same_site_hints: tuple[SameSiteOrgLocationHint, ...] = (),
) -> str:
    allowed = sorted(auto_link_natures_for_pair(from_type, to_type))
    from_section = "\n".join(_format_entity_block(e) for e in from_entities) or "(none)"
    to_section = "\n".join(_format_entity_block(e) for e in to_entities) or "(none)"
    snippet_section = (
        "\n".join(f'- "{s}"' for s in pair_snippets) if pair_snippets else "(none)"
    )
    prompt_version = (
        AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS
        if same_site_hints
        else AUTO_CONNECTION_PROMPT_VERSION_NATURE_CATALOG
    )
    hints_section = _format_same_site_hints_section(same_site_hints)
    same_site_rules = ""
    if same_site_hints:
        same_site_rules = (
            "- For candidate same-site pairs, return located_at when the text places the "
            "organization at that named place (not only a parent district or city).\n"
        )
    return (
        f"prompt_version: {prompt_version}\n"
        f"Identify explicit relationships from {from_type} to {to_type}.\n\n"
        f"Allowed nature slugs (optional; use only when one clearly fits): "
        f"{', '.join(allowed) if allowed else '(none)'}\n\n"
        "Rules:\n"
        "- Return an edge only when the article states or strongly entails a direct "
        "relationship between the two entities.\n"
        "- Do not create edges for co-mention, same paragraph, same event attendance, "
        "same geography, same topic, or generic association.\n"
        "- Prefer no edge over an uncertain edge.\n"
        "- Use only canonical ids from the lists below.\n"
        "- Each edge must include a supporting quote copied from the snippets.\n"
        "- Each edge must include description: one sentence or less explaining the "
        "relationship in narrative terms.\n"
        "- Set nature to one allowed slug only when it clearly fits; otherwise use null.\n"
        "- confidence must be 0.0-1.0; only return edges you would score >= 0.9.\n"
        "- Multiple edges for the same pair+nature are not needed; one edge with the best "
        "quote is enough (systems will attach further articles as evidence).\n"
        "- For organization→location, prefer located_at over based_in when a specific "
        "address/place is supported.\n"
        "- For person→organization, prefer leads over works_for when leadership is explicit.\n"
        "- Athletes on a sports team: use plays_for (not member_of).\n"
        "- Coaches of a sports team: use coaches (not works_for or leads).\n"
        "- Mayors, governors, sheriffs, and similar executives of a jurisdiction: use "
        "holds_office_in (not represents).\n"
        "- Elected legislators for a district: use represents to that location.\n"
        "- Person→location must not use address-like locations.\n"
        "- Prefer the most specific supported geography.\n"
        "- Never connect an entity to itself.\n"
        "- For symmetric relationships, return one edge per pair.\n"
        f"{same_site_rules}"
        f"{hints_section}"
        f"From entities ({from_type}):\n{from_section}\n\n"
        f"To entities ({to_type}):\n{to_section}\n\n"
        f"Evidence snippets:\n{snippet_section}\n\n"
        'Return JSON only: {"edges": [{"from_entity_id": "...", "to_entity_id": "...", '
        '"description": "...", "nature": null, "confidence": 0.95, "quote": "...", '
        '"reason": "..."}]}'
    )


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
