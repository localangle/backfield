"""Token-based person name overlap for recall and catalog search."""

from __future__ import annotations

import re

from backfield_stylebook.entities.person.types import normalize_person_text

_WS_RE = re.compile(r"\s+")
# Single letter or letter+period (middle initial).
_MIDDLE_INITIAL_RE = re.compile(r"^[a-z]\.?$")


def person_name_tokens(display_name: str) -> tuple[str | None, str | None, list[str]]:
    """Parse ``(given, family, significant_tokens)`` from a display name."""
    norm = normalize_person_text(display_name)
    if not norm:
        return None, None, []
    raw_parts = [p for p in _WS_RE.split(norm) if p]
    significant: list[str] = []
    for part in raw_parts:
        cleaned = part.rstrip(".")
        if not cleaned:
            continue
        if _MIDDLE_INITIAL_RE.fullmatch(cleaned) and len(raw_parts) > 1:
            continue
        significant.append(cleaned)
    if not significant:
        return None, None, []
    if len(significant) == 1:
        return significant[0], significant[0], significant
    given = significant[0]
    family = significant[-1]
    return given, family, significant


def _given_names_compatible(a: str, b: str) -> bool:
    """True when given names are equal or one is a prefix of the other (min 2 chars)."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 2:
        return False
    return long.startswith(short)


def score_person_name_overlap(
    query_name: str,
    candidate_name: str,
    *,
    extra_candidate_names: list[str] | None = None,
) -> int:
    """Higher is better; 0 means no meaningful name overlap."""
    q_given, q_family, q_tokens = person_name_tokens(query_name)
    if not q_tokens:
        return 0
    best = 0
    names_to_check = [candidate_name, *(extra_candidate_names or [])]
    for cand in names_to_check:
        c_given, c_family, c_tokens = person_name_tokens(cand)
        if not c_tokens:
            continue
        score = 0
        q_norm = normalize_person_text(query_name)
        c_norm = normalize_person_text(cand)
        if q_norm and c_norm and q_norm == c_norm:
            score = 100
        elif q_norm and c_norm and (q_norm in c_norm or c_norm in q_norm):
            score = max(score, 40)
        if q_family and c_family and q_family == c_family:
            score += 50
            if q_given and c_given and _given_names_compatible(q_given, c_given):
                score += 40
        elif q_given and c_given and _given_names_compatible(q_given, c_given):
            score += 25
        q_set = set(q_tokens)
        c_set = set(c_tokens)
        if q_set and c_set and q_set.intersection(c_set):
            score += 15
        best = max(best, score)
    return best


def significant_search_tokens(query: str) -> list[str]:
    """Tokens worth using in catalog ``ILIKE`` search (surname + given names)."""
    _given, family, tokens = person_name_tokens(query)
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if len(tok) < 2:
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    if family and family not in seen and len(family) >= 2:
        out.insert(0, family)
    return out[:6]
