"""Prompt helpers for chunk-aware extraction and whole-document truncation guards."""

from __future__ import annotations

from typing import Any

from agate_utils.text_chunking import DocumentChunk, truncate_text_to_tokens

# Alternate body fields that can reintroduce the full document into prompts.
BODY_ALIAS_KEYS: frozenset[str] = frozenset(
    {
        "article_text",
        "articleBody",
        "article_body",
        "richTextBody",
        "rich_text",
        "body",
        "content",
        "story",
        "full_text",
        "html",
    }
)


def sanitize_body_aliases_for_prompt(
    flattened: dict[str, Any],
    *,
    prompt_text: str,
) -> dict[str, Any]:
    """Copy flattened state with body aliases replaced by the prompt-facing text."""
    out = dict(flattened)
    out["text"] = prompt_text
    for key in BODY_ALIAS_KEYS:
        if key in out and isinstance(out[key], str) and out[key].strip():
            out[key] = prompt_text
    return out


def apply_chunk_text_to_flattened(
    flattened: dict[str, Any],
    *,
    chunk_text: str,
) -> dict[str, Any]:
    """Return flattened state where ``text`` and body aliases are the chunk text."""
    return sanitize_body_aliases_for_prompt(flattened, prompt_text=chunk_text)


def build_chunk_analysis_text(chunk: DocumentChunk, source_text: str) -> str:
    """Format owned text with labeled overlap context for the model."""
    owned = source_text[chunk.ownership_start : chunk.ownership_end]
    before = source_text[chunk.context_start : chunk.ownership_start]
    after = source_text[chunk.ownership_end : chunk.context_end]

    sections: list[str] = []
    if before.strip():
        sections.append(
            "## Preceding context (for disambiguation only; do not extract solely from here)\n\n"
            + before.rstrip()
        )
    sections.append(
        "## Text to analyze (owned segment — every extracted record must be grounded here)\n\n"
        + owned
    )
    if after.strip():
        sections.append(
            "## Following context (for disambiguation only; do not extract solely from here)\n\n"
            + after.lstrip()
        )
    return "\n\n".join(sections)


def truncate_flattened_for_prompt(
    flattened: dict[str, Any],
    *,
    max_tokens: int,
) -> tuple[dict[str, Any], bool]:
    """Truncate canonical text (and body aliases) for whole-document prompt-only use."""
    text = flattened.get("text")
    if not isinstance(text, str):
        text = ""
    truncated, was_truncated = truncate_text_to_tokens(text, max_tokens)
    return sanitize_body_aliases_for_prompt(flattened, prompt_text=truncated), was_truncated
