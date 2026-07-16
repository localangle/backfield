"""Token-based person name overlap for recall and catalog search."""

from __future__ import annotations

import re

from backfield_entities.entities.person.types import (
    normalize_person_text,
    person_match_key,
    person_names_match,
)

_WS_RE = re.compile(r"\s+")
# Single letter or letter+period (middle initial).
_MIDDLE_INITIAL_RE = re.compile(r"^[a-z]\.?$")
_PERSON_GENERATIONAL_SUFFIX_TOKENS: frozenset[str] = frozenset(
    {"jr", "sr", "ii", "iii", "iv", "junior", "senior"}
)
# Particles often preceding a core surname (compare terminal core after stripping these).
_FAMILY_NAME_PARTICLES: frozenset[str] = frozenset(
    {
        "de",
        "da",
        "di",
        "del",
        "della",
        "der",
        "den",
        "van",
        "von",
        "la",
        "le",
        "el",
        "al",
        "st",
        "ste",
    }
)

# High-confidence English nickname groups where prefix checks fail (Tom/Thomas).
_GIVEN_NAME_NICKNAME_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"tom", "thomas", "tommy"}),
    frozenset({"rob", "robert", "bob", "bobby"}),
    frozenset({"bill", "william", "will", "billy", "liam"}),
    frozenset({"dick", "richard", "rick", "ricky"}),
    frozenset({"jim", "james", "jimmy", "jamie"}),
    frozenset({"mike", "michael", "mick"}),
    frozenset({"joe", "joseph", "joey"}),
    frozenset({"dave", "david"}),
    frozenset({"dan", "daniel", "danny"}),
    frozenset({"chris", "christopher", "kit"}),
    frozenset({"matt", "matthew"}),
    frozenset({"steve", "stephen", "steven"}),
    frozenset({"beth", "elizabeth", "liz", "betty", "eliza"}),
    frozenset({"kate", "catherine", "katherine", "kathy", "cathy"}),
    frozenset({"alex", "alexander", "alexandra"}),
)

_GIVEN_NAME_TO_NICKNAME_GROUP: dict[str, int] = {
    name: idx
    for idx, group in enumerate(_GIVEN_NAME_NICKNAME_GROUPS)
    for name in group
}


def person_name_tokens(display_name: str) -> tuple[str | None, str | None, list[str]]:
    """Parse ``(given, family, significant_tokens)`` from a display name."""
    norm = person_match_key(display_name)
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


def given_names_compatible(a: str, b: str) -> bool:
    """True when given names are equal, nicknames, or one is a prefix of the other."""
    if not a or not b:
        return False
    if a == b:
        return True
    group_a = _GIVEN_NAME_TO_NICKNAME_GROUP.get(a)
    group_b = _GIVEN_NAME_TO_NICKNAME_GROUP.get(b)
    if group_a is not None and group_a == group_b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 2:
        return False
    return long.startswith(short)


def person_identity_name_parts(
    display_name: str,
) -> tuple[str | None, str | None, list[str]]:
    """Parse ``(given, family_core, significant_tokens)`` with suffix/particle awareness.

    Generational suffixes are stripped before selecting the family token. Leading
    surname particles (``van``, ``de``, …) are dropped so ``Juan de la Cruz`` and
    ``Juan Cruz`` share a core family token for conflict checks.
    """
    given, _family, tokens = person_name_tokens(display_name)
    if not tokens:
        return None, None, []
    working = list(tokens)
    while working and working[-1] in _PERSON_GENERATIONAL_SUFFIX_TOKENS:
        working.pop()
    if not working:
        return None, None, tokens
    if len(working) == 1:
        return working[0], working[0], tokens
    family_core = working[-1]
    # Drop leading particles when there is still a non-particle core left.
    head = working[1:-1]
    while head and head[0] in _FAMILY_NAME_PARTICLES:
        head = head[1:]
    # If the terminal token itself is only a particle with no core, keep it.
    if family_core in _FAMILY_NAME_PARTICLES and head:
        family_core = head[-1]
    id_given = working[0]
    return id_given, family_core, tokens


# Backward-compatible private alias.
_given_names_compatible = given_names_compatible


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
        if person_names_match(query_name, cand):
            score = 100
        else:
            q_norm = normalize_person_text(query_name)
            c_norm = normalize_person_text(cand)
            if q_norm and c_norm and (q_norm in c_norm or c_norm in q_norm):
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
