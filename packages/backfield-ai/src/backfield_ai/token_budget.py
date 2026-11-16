"""Count and truncate text in real tokens (OpenAI ``cl100k_base``, as used by LiteLLM)."""

from __future__ import annotations

import litellm

# Unicode replacement character left behind when a cut lands inside a multi-byte character.
_REPLACEMENT_CHARACTER = "\ufffd"


def count_tokens(text: str) -> int:
    """Exact token count; special-token look-alikes in article text are counted as plain text."""
    return len(litellm.encoding.encode(text, disallowed_special=()))


def truncate_to_token_limit(text: str, max_tokens: int) -> tuple[str, bool]:
    """Return ``(text, truncated)`` with ``text`` cut to at most ``max_tokens`` tokens."""
    if max_tokens <= 0:
        return "", bool(text)
    tokens = litellm.encoding.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return text, False
    cut = litellm.encoding.decode(tokens[:max_tokens]).rstrip(_REPLACEMENT_CHARACTER).rstrip()
    return cut, True
