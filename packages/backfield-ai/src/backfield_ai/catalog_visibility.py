"""Which catalog rows belong on language-model lists versus specialized kinds."""

from __future__ import annotations

from backfield_ai.constants import (
    AI_CAPABILITY_DECISION,
    AI_CAPABILITY_EMBEDDING,
    AI_MODEL_KIND_DECISION,
    AI_MODEL_KIND_EMBEDDING,
)

# Kinds that stay off language-model pickers unless a caller asks for them by capability.
SPECIALIZED_MODEL_KINDS: frozenset[str] = frozenset(
    {AI_MODEL_KIND_DECISION, AI_MODEL_KIND_EMBEDDING}
)

_KIND_CAPABILITY: dict[str, str] = {
    AI_MODEL_KIND_DECISION: AI_CAPABILITY_DECISION,
    AI_MODEL_KIND_EMBEDDING: AI_CAPABILITY_EMBEDDING,
}


def is_language_model_kind(model_kind: str) -> bool:
    """True for generative rows and older language rows that are not a specialized kind."""
    return model_kind.strip() not in SPECIALIZED_MODEL_KINDS


def matches_capability_request(
    *,
    model_kind: str,
    capabilities: list[str],
    requested: set[str],
) -> bool:
    """Return whether a catalog row belongs in a capability-filtered model list.

    An empty request is the unfiltered catalog (project model settings). Decision and
    embedding rows appear in a filtered list only when that list asks for their capability.
    """
    kind = model_kind.strip()
    owned = {str(cap).strip() for cap in capabilities if str(cap).strip()}
    specialized = _KIND_CAPABILITY.get(kind)
    if not requested:
        return True
    if specialized is not None:
        return specialized in requested and requested.issubset(owned)
    if requested & set(_KIND_CAPABILITY.values()):
        return False
    return requested.issubset(owned)


def include_in_language_model_list(*, model_kind: str, capabilities: list[str]) -> bool:
    """Stylebook and other language-model menus: hide decision and embedding rows."""
    if not is_language_model_kind(model_kind):
        return False
    owned = {str(cap).strip().lower() for cap in capabilities if str(cap).strip()}
    if owned and not (owned & {"text", "json"}):
        return False
    return True
