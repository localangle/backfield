"""PersonExtract prompt source resolution and placeholder substitution."""

from __future__ import annotations

from agate_nodes.place_extract.prompt_template import (
    resolve_place_extract_prompt as resolve_person_extract_prompt,
)
from agate_nodes.place_extract.prompt_template import (
    substitute_prompt_placeholders,
)

__all__ = ["resolve_person_extract_prompt", "substitute_prompt_placeholders"]
