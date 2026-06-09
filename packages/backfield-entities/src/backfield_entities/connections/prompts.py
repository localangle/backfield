"""Prompt builders for automatic connection classification."""

from __future__ import annotations

from backfield_entities.connections.same_site_hints import SameSiteOrgLocationHint
from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_PROMPT_VERSION,
    AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS,
    auto_link_natures_for_pair,
)
from backfield_entities.connections.types import LinkedEntitySnapshot


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
        "- When confirmed, prefer located_at and include match_basis head_name_match in reason."
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
        else AUTO_CONNECTION_PROMPT_VERSION
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
        f"Classify explicit relationships from {from_type} to {to_type} using ONLY the "
        f"allowed nature slugs.\n\n"
        f"Allowed natures: {', '.join(allowed)}\n\n"
        "Rules:\n"
        "- Return edges only when the evidence explicitly supports the relationship.\n"
        "- Do not infer from co-mention alone.\n"
        "- Prefer no edge over an uncertain edge.\n"
        "- Use only canonical ids from the lists below.\n"
        "- Each edge must include a supporting quote copied from the snippets.\n"
        "- confidence must be 0.0-1.0; only return edges you would score >= 0.9.\n"
        "- Multiple natures for the same pair are allowed only when each is explicitly "
        "supported by separate evidence.\n"
        "- For organization→location, prefer located_at over based_in when a specific "
        "address/place is supported.\n"
        "- For person→organization, prefer leads over works_for when leadership is explicit.\n"
        "- Athletes and coaches: team nicknames before a player name or role descriptor "
        '(e.g. "Phillies masher Kyle Schwarber") support member_of to that sports_team.\n'
        "- Person→location must not use address-like locations.\n"
        "- Prefer the most specific supported geography.\n"
        f"{same_site_rules}"
        f"{hints_section}"
        f"From entities ({from_type}):\n{from_section}\n\n"
        f"To entities ({to_type}):\n{to_section}\n\n"
        f"Evidence snippets:\n{snippet_section}\n\n"
        'Return JSON only: {"edges": [{"from_entity_id": "...", "to_entity_id": "...", '
        '"nature": "...", "confidence": 0.95, "quote": "...", "reason": "..."}]}'
    )
