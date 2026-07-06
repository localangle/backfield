"""Accent- and apostrophe-insensitive text normalization for catalog matching."""

from __future__ import annotations

import re
import unicodedata

_UNICODE_APOSTROPHE_CHARS = "\u2018\u2019\u02bc\u0060"
_WS_RE = re.compile(r"\s+")


def normalize_unicode_apostrophes(value: str) -> str:
    for ch in _UNICODE_APOSTROPHE_CHARS:
        value = value.replace(ch, "'")
    return value


def fold_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_match_text(value: str | None) -> str:
    """Lowercase single-spaced text with ASCII apostrophes."""
    if value is None:
        return ""
    cleaned = normalize_unicode_apostrophes(str(value).strip())
    return _WS_RE.sub(" ", cleaned).lower()


def match_fold_key(value: str | None) -> str:
    """Accent-insensitive key for equality and fuzzy recall."""
    normalized = normalize_match_text(value)
    if not normalized:
        return ""
    return fold_accents(normalized)


def alias_lookup_keys(value: str | None) -> tuple[str, ...]:
    """Stored ``normalized_alias`` variants: literal normalized plus folded when different."""
    norm = normalize_match_text(value)
    if not norm:
        return ()
    folded = match_fold_key(value)
    if folded != norm:
        return (norm, folded)
    return (norm,)


def escape_ilike_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
