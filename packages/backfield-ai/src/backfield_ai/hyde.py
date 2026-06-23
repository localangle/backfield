"""Hypothetical Document Embeddings (HyDE) for semantic search queries."""

from __future__ import annotations

from sqlmodel import Session

from backfield_ai.completions import complete_text_for_model_config
from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.model_resolve import resolve_semantic_hyde_model_config_id

_HYDE_SYSTEM_MESSAGE = (
    "You write short news article passages for semantic search indexing. "
    "Given a search query, write a plausible news story excerpt that would be a "
    "strong match for that query. Write only the passage body—no titles, labels, "
    "or meta commentary."
)


def generate_hypothetical_document(
    session: Session,
    *,
    project_id: int,
    query: str,
) -> tuple[str, str, str]:
    """Return (hypothetical_document, hyde_model_config_id, hyde_litellm_model)."""
    text = query.strip()
    if not text:
        raise EmbeddingConfigurationError("Search query text is required.")

    model_config_id = resolve_semantic_hyde_model_config_id(session, project_id)
    result = complete_text_for_model_config(
        session,
        project_id=project_id,
        model_config_id=model_config_id,
        messages=[
            {"role": "system", "content": _HYDE_SYSTEM_MESSAGE},
            {"role": "user", "content": f"Search query:\n{text}\n\nHypothetical article passage:"},
        ],
        max_tokens=2048,
        temperature=0.2,
        force_json_response=False,
    )
    passage = result.text.strip()
    if not passage:
        model_label = (
            f"{result.provider}/{result.provider_model_id}"
            if result.provider and result.provider != "unknown"
            else result.provider_model_id
        )
        raise EmbeddingConfigurationError(
            "HyDE generation returned empty text "
            f"(model={model_label!r}). Try another generative default or retry.",
        )
    if result.provider and result.provider != "unknown":
        hyde_litellm_model = f"{result.provider}/{result.provider_model_id}"
    else:
        hyde_litellm_model = result.provider_model_id
    return passage, model_config_id, hyde_litellm_model
