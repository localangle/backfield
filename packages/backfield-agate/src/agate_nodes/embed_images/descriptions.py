"""Compose image descriptions from upstream text fields (no vision input)."""

from __future__ import annotations

from typing import Any

DEFAULT_PROMPT = (
    "Write a clear, detailed description of the image using only the caption and article "
    "context provided. Do not invent visual details that are not supported by the context."
)

MAX_ARTICLE_CONTEXT_CHARS = 2000


def _clean_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def image_text_fields(image_obj: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return caption, alt, and description from an upstream image object."""
    caption = _clean_text(image_obj.get("caption"))
    alt = _clean_text(image_obj.get("alt"))
    description = _clean_text(image_obj.get("description"))
    return caption, alt, description


def build_description_prompt(
    prompt: str,
    *,
    caption: str | None,
    alt: str | None,
    description: str | None,
    article_text: str | None,
) -> str:
    """Build a text-only LLM prompt from image metadata and article context."""
    instruction = prompt.strip() or DEFAULT_PROMPT
    context_parts: list[str] = []
    if description:
        context_parts.append(f"Existing description: {description}")
    if caption:
        context_parts.append(f"Caption: {caption}")
    if alt and alt != caption:
        context_parts.append(f"Alt text: {alt}")
    if article_text:
        truncated = article_text[:MAX_ARTICLE_CONTEXT_CHARS]
        if len(article_text) > MAX_ARTICLE_CONTEXT_CHARS:
            truncated += "..."
        context_parts.append(f"Article text: {truncated}")

    if not context_parts:
        return instruction

    return instruction + "\n\nContext:\n" + "\n".join(context_parts)
