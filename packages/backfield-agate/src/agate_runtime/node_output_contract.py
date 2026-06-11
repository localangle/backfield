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

# Nodes whose run JSON is the full payload: inputs (article source) and DBOutput
# (consolidated persisted body + persist summaries).
FULL_OUTPUT_NODE_TYPES: frozenset[str] = INPUT_NODE_TYPES | frozenset({"DBOutput"})

# Explicit owned keys for run JSON. When unset, non-passthrough keys are kept.
NODE_CONTRIBUTION_KEYS: dict[str, frozenset[str]] = {
    "ArticleMetadata": frozenset({"article_metadata"}),
    "CustomExtract": frozenset({"custom_records"}),
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
    if node_type in FULL_OUTPUT_NODE_TYPES:
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


def project_gathered_branch_refs(
    gathered: dict[str, Any],
    *,
    source_id_to_public: dict[str, str],
    execution_order: list[str],
) -> list[str]:
    """Return public node slugs gathered by a sync barrier (no payload duplication)."""
    refs: list[str] = []
    seen: set[str] = set()
    for node_id in execution_order:
        if node_id not in gathered:
            continue
        public_key = source_id_to_public.get(node_id, node_id)
        if public_key in seen:
            continue
        refs.append(public_key)
        seen.add(public_key)
    for source_id in gathered:
        public_key = source_id_to_public.get(source_id, source_id)
        if public_key in seen:
            continue
        refs.append(public_key)
        seen.add(public_key)
    return refs
