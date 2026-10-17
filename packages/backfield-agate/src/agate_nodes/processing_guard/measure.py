"""Deterministic Processing Guard measurements.

Word count is exact for body text. Entity volume is a versioned estimate of
name-like references, not a catalog of real entities.
"""

from __future__ import annotations

import re

DETECTOR_VERSION = "name_span_v1"

# Capitalized function words that start sentences but are not names.
_NAME_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "after",
        "also",
        "before",
        "but",
        "for",
        "from",
        "her",
        "here",
        "his",
        "how",
        "its",
        "not",
        "or",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "week",
        "what",
        "when",
        "where",
        "who",
        "with",
    }
)

# Particles that may sit inside a multi-word name without starting a new span.
_NAME_PARTICLES = frozenset({"da", "de", "del", "di", "la", "le", "of", "van", "von"})

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)
_TOKEN_RE = re.compile(
    r"[^\W\d_]+(?:['’.-][^\W\d_]+)*|[0-9]+(?:st|nd|rd|th)?|[,;:]",
    re.UNICODE,
)


def count_words(text: str) -> int:
    """Count letter-bearing words in body text."""
    if not text:
        return 0
    return sum(1 for _ in _WORD_RE.finditer(text))


def _is_name_word(token: str) -> bool:
    if not token or not token[0].isupper():
        return False
    if token.lower() in _NAME_STOPWORDS:
        return False
    return any(char.isalpha() for char in token)


def estimate_entity_references(text: str) -> int:
    """Count name-like spans. Repeated names each count again.

    A span is one or more capitalized words, optionally joined by a small set of
    name particles (``van``, ``of``, ``de``). Commas, semicolons, and colons
    start a new reference, so ``Jalen Dupree, Penn Manor`` counts as two.
    The count is an estimate used to decide whether extraction output may be
    too large.
    """
    if not text:
        return 0
    tokens = [match.group(0) for match in _TOKEN_RE.finditer(text)]
    spans = 0
    index = 0
    while index < len(tokens):
        if not _is_name_word(tokens[index]):
            index += 1
            continue
        spans += 1
        index += 1
        while index < len(tokens):
            lowered = tokens[index].lower()
            if (
                lowered in _NAME_PARTICLES
                and index + 1 < len(tokens)
                and _is_name_word(tokens[index + 1])
            ):
                index += 2
                continue
            if _is_name_word(tokens[index]):
                index += 1
                continue
            break
    return spans
