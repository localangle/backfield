"""Post-processing rules for proposed automatic connections."""

from __future__ import annotations

from collections import defaultdict

from backfield_entities.connections.types import AutoConnectionEdgeProposal


def apply_subsumption_rules(
    edges: list[AutoConnectionEdgeProposal],
) -> list[AutoConnectionEdgeProposal]:
    """Drop redundant natures for the same canonical pair in one run."""
    grouped: dict[tuple[str, str], list[AutoConnectionEdgeProposal]] = defaultdict(list)
    for edge in edges:
        grouped[(edge.from_entity_id, edge.to_entity_id)].append(edge)

    out: list[AutoConnectionEdgeProposal] = []
    for group in grouped.values():
        natures = {edge.nature for edge in group if edge.nature}
        filtered = list(group)
        if "leads" in natures and "works_for" in natures:
            filtered = [edge for edge in filtered if edge.nature != "works_for"]
        if "located_at" in natures and "based_in" in natures:
            filtered = [edge for edge in filtered if edge.nature != "based_in"]
        out.extend(filtered)
    return out
