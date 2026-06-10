"""Which keys each node type owns in run JSON (vs article passthrough)."""

from __future__ import annotations

from typing import Any

from agate_runtime.output_node import PREFERRED_KEY_ORDER

# Article fields copied downstream for LLM context — not repeated in enrich-node run JSON.
ARTICLE_PASSTHROUGH_KEYS: frozenset[str] = frozenset(
    [
        *PREFERRED_KEY_ORDER,
        "entry_id",
    ]
)

# Source nodes emit the full article payload once.
INPUT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "JSONInput",
        "TextInput",
        "S3Input",
    }
)

# Explicit owned keys for run JSON. When unset, non-passthrough keys are kept.
NODE_CONTRIBUTION_KEYS: dict[str, frozenset[str]] = {
    "ArticleMetadata": frozenset({"article_metadata"}),
    "EmbedImages": frozenset({"image_embeddings"}),
    "EmbedText": frozenset({"article_embedding"}),
    "PlaceExtract": frozenset({"locations"}),
    "PersonExtract": frozenset({"people"}),
    "OrganizationExtract": frozenset({"organizations"}),
    "GeocodeAgent": frozenset({"places"}),
    "Gather": frozenset({"gathered"}),
    "Output": frozenset({"consolidated"}),
}


def contribution_keys_for_node(node_type: str, output: dict[str, Any]) -> frozenset[str]:
    if node_type in INPUT_NODE_TYPES:
        return frozenset(output.keys())
    explicit = NODE_CONTRIBUTION_KEYS.get(node_type)
    if explicit is not None:
        return frozenset(key for key in explicit if key in output)
    return frozenset(key for key in output if key not in ARTICLE_PASSTHROUGH_KEYS)


def project_node_contribution(node_type: str, output: dict[str, Any]) -> dict[str, Any]:
    """Return only keys this node adds for run JSON (one representation per node)."""
    if not isinstance(output, dict):
        return {}
    keys = contribution_keys_for_node(node_type, output)
    return {key: output[key] for key in keys if key in output}


def project_gathered_contributions(
    gathered: dict[str, Any],
    *,
    source_id_to_type: dict[str, str],
    source_id_to_public: dict[str, str],
) -> dict[str, Any]:
    """Map gathered branch payloads to public slugs with contribution-only values."""
    projected: dict[str, Any] = {}
    for source_id, payload in gathered.items():
        if not isinstance(payload, dict):
            continue
        public_key = source_id_to_public.get(source_id, source_id)
        node_type = source_id_to_type.get(source_id, "")
        projected[public_key] = project_node_contribution(node_type, payload)
    return projected
