"""Name-variant signals for the ``duplicate-people`` check.

Exact and punctuation-level variants are handled in :mod:`_person_duplicate_signals`.
This module covers variants that need a second signal before they are worth a reviewer's time:

* ``nickname``: ``Hank Aaron`` and ``Henry Aaron``
* ``middle_initial``: ``Robert S Abbott`` and ``Robert Sengstacke Abbott``
* ``dropped_middle``: ``Jennifer Cotto Johnson`` and ``Jennifer Johnson``
* ``compound_surname``: ``Maggie Daly`` and ``Maggie Daly Skogsbakken``
* ``spelling``: ``Shepshu Aakhu`` and ``Shepsu Aakhu`` (one letter differs in one name word)

A shared name variant alone is not enough: ``John Adams`` and ``John Quincy Adams`` are
different people. Each kind states what must also agree (affiliation, or affiliation-less
records of the same person type).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

NameVariantKind = Literal[
    "nickname", "middle_initial", "dropped_middle", "compound_surname", "spelling"
]

# Shorter words are too often different names (``Jon``/``Jan``, ``Marc``/``Mark``).
_SPELLING_MIN_WORD_LENGTH = 5
_SPELLING_MAX_NAME_WORDS = 4

# Informal first name -> formal first name. Deliberately conservative: names that are
# ambiguous on their own (``al``, ``sandy``, ``jamie``, ``will``, ``terry``) are left out.
FIRST_NAME_ALIASES: dict[str, str] = {
    "mike": "michael",
    "mick": "michael",
    "bill": "william",
    "billy": "william",
    "willie": "william",
    "bob": "robert",
    "bobby": "robert",
    "rob": "robert",
    "robbie": "robert",
    "dick": "richard",
    "rick": "richard",
    "rich": "richard",
    "ricky": "richard",
    "jim": "james",
    "jimmy": "james",
    "joe": "joseph",
    "joey": "joseph",
    "tom": "thomas",
    "tommy": "thomas",
    "dave": "david",
    "dan": "daniel",
    "danny": "daniel",
    "chris": "christopher",
    "tony": "anthony",
    "steve": "steven",
    "stephen": "steven",
    "matt": "matthew",
    "andy": "andrew",
    "ben": "benjamin",
    "sam": "samuel",
    "nick": "nicholas",
    "pat": "patrick",
    "trish": "patricia",
    "liz": "elizabeth",
    "beth": "elizabeth",
    "betsy": "elizabeth",
    "lizzie": "elizabeth",
    "kate": "katherine",
    "katie": "katherine",
    "kathy": "katherine",
    "katharine": "katherine",
    "kathryn": "katherine",
    "cathy": "catherine",
    "sue": "susan",
    "jenny": "jennifer",
    "jen": "jennifer",
    "debbie": "deborah",
    "deb": "deborah",
    "peggy": "margaret",
    "maggie": "margaret",
    "meg": "margaret",
    "ted": "edward",
    "ed": "edward",
    "eddie": "edward",
    "ron": "ronald",
    "ronnie": "ronald",
    "don": "donald",
    "greg": "gregory",
    "jeff": "jeffrey",
    "charlie": "charles",
    "chuck": "charles",
    "hank": "henry",
    "jack": "john",
    "johnny": "john",
    "larry": "lawrence",
    "phil": "philip",
    "fred": "frederick",
    "frank": "francis",
    "tim": "timothy",
    "ken": "kenneth",
    "kenny": "kenneth",
    "alex": "alexander",
    "becky": "rebecca",
    "pete": "peter",
    "zach": "zachary",
    "josh": "joshua",
    "nate": "nathaniel",
    "manny": "manuel",
    "pancho": "francisco",
    "paco": "francisco",
    "pepe": "jose",
    "beto": "alberto",
    "lupe": "guadalupe",
    "chuy": "jesus",
}

_QUOTED_NICKNAME_RE = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{1,30})[\"\u201c\u201d]")
_AFFILIATION_NOISE: frozenset[str] = frozenset(
    {"the", "of", "and", "a", "an", "inc", "llc", "co", "corp", "company"}
)
_GENERIC_AFFILIATION_WORDS: frozenset[str] = frozenset(
    {
        "administration",
        "agency",
        "association",
        "board",
        "bureau",
        "city",
        "college",
        "committee",
        "council",
        "county",
        "department",
        "dept",
        "district",
        "fire",
        "government",
        "group",
        "office",
        "police",
        "school",
        "schools",
        "state",
        "team",
        "university",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def formal_first_name(token: str) -> str:
    """Return the formal form of an informal first name, or the token itself."""
    return FIRST_NAME_ALIASES.get(token, token)


def _fold(value: str | None) -> str:
    if not value:
        return ""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)
    )
    return stripped.casefold()


def affiliation_tokens(value: str | None) -> frozenset[str]:
    return frozenset(
        token for token in _TOKEN_RE.findall(_fold(value)) if token not in _AFFILIATION_NOISE
    )


def _distinctive_affiliation_tokens(value: str | None) -> frozenset[str]:
    return affiliation_tokens(value) - _GENERIC_AFFILIATION_WORDS


def affiliations_agree(left: str | None, right: str | None) -> bool:
    """True when both affiliations name the same organization, or one is a fuller form of the other.

    Generic words (``department``, ``office``) are ignored, so ``Chicago Fire Department``
    and ``Evanston Fire Department`` do not agree, while ``Casa DuPage`` and
    ``Casa DuPage Workers Center`` do.
    """
    left_tokens, right_tokens = (
        _distinctive_affiliation_tokens(left),
        _distinctive_affiliation_tokens(right),
    )
    return bool(
        left_tokens
        and right_tokens
        and (left_tokens <= right_tokens or right_tokens <= left_tokens)
    )


def affiliations_both_absent(left: str | None, right: str | None) -> bool:
    return not affiliation_tokens(left) and not affiliation_tokens(right)


def quoted_nicknames(label: str) -> tuple[str, ...]:
    """Nicknames written in quotes inside a label, e.g. ``Edward "Eddie" Acevedo``."""
    return tuple(match.strip() for match in _QUOTED_NICKNAME_RE.findall(label) if match.strip())


def strip_quoted_nicknames(label: str) -> str:
    return " ".join(_QUOTED_NICKNAME_RE.sub(" ", label).split())


def _initial_matches(short: str, long: str) -> bool:
    return short == long or (len(short) == 1 and long.startswith(short))


def _middles_are_initial_expansion(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """True when middle tokens pair up, differ, and each pair is an initial and its full name."""
    if len(left) != len(right) or not left or left == right:
        return False
    return all(
        _initial_matches(a, b) or _initial_matches(b, a) for a, b in zip(left, right, strict=True)
    )


def _is_one_letter_edit(left: str, right: str) -> bool:
    """One substitution, insertion, deletion, or swap of two neighbouring letters."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differing = [i for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        if len(differing) == 1:
            return True
        return (
            len(differing) == 2
            and differing[1] == differing[0] + 1
            and left[differing[0]] == right[differing[1]]
            and left[differing[1]] == right[differing[0]]
        )
    shorter, longer = sorted((left, right), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def _is_spelling_variant(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Same words except one that differs by a single letter (same first letter, long enough)."""
    if len(left) != len(right) or not 2 <= len(left) <= _SPELLING_MAX_NAME_WORDS:
        return False
    differing = [i for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
    if len(differing) != 1:
        return False
    a, b = left[differing[0]], right[differing[0]]
    return (
        min(len(a), len(b)) >= _SPELLING_MIN_WORD_LENGTH
        and a.isalpha()
        and b.isalpha()
        and a[0] == b[0]
        and _is_one_letter_edit(a, b)
    )


def spelling_blocking_keys(core_tokens: tuple[str, ...]) -> frozenset[str]:
    """Keys that let names one letter apart meet: each long word with one letter removed.

    ``shepshu`` with ``h`` removed equals ``shepsu``, so both records share a key. Scoring then
    confirms the pair is a real one-letter spelling variant.
    """
    if not 2 <= len(core_tokens) <= _SPELLING_MAX_NAME_WORDS:
        return frozenset()
    keys: set[str] = set()
    for position, word in enumerate(core_tokens):
        if len(word) < _SPELLING_MIN_WORD_LENGTH or not word.isalpha():
            continue
        before = " ".join(core_tokens[:position])
        after = " ".join(core_tokens[position + 1 :])
        for index in range(len(word)):
            keys.add(f"spell:{position}:{before}|{word[:index] + word[index + 1 :]}|{after}")
        keys.add(f"spell:{position}:{before}|{word}|{after}")
    return frozenset(keys)


def name_variant_kind(left: tuple[str, ...], right: tuple[str, ...]) -> NameVariantKind | None:
    """Classify two core name token tuples (titles and suffixes already removed).

    Returns ``None`` for identical names (handled elsewhere) and for names that are not variants.
    """
    if len(left) < 2 or len(right) < 2 or left == right:
        return None
    if _is_spelling_variant(left, right):
        return "spelling"
    if formal_first_name(left[0]) != formal_first_name(right[0]):
        return None
    first_differs = left[0] != right[0]
    if left[1:] == right[1:]:
        return "nickname" if first_differs else None
    if left[-1] != right[-1]:
        return _compound_surname_kind(left, right)
    if _middles_are_initial_expansion(left[1:-1], right[1:-1]):
        return "middle_initial"
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) == 2 and len(longer) > 2 and len(longer[1]) > 1:
        return "dropped_middle"
    return None


def _compound_surname_kind(left: tuple[str, ...], right: tuple[str, ...]) -> NameVariantKind | None:
    """``Maggie Daly`` against ``Maggie Daly Skogsbakken``: the longer name adds a last word."""
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) == 2 and len(longer) == 3 and longer[1] == shorter[1] and len(longer[2]) > 1:
        return "compound_surname"
    return None


def name_variant_is_corroborated(
    kind: NameVariantKind,
    *,
    left_affiliation: str | None,
    right_affiliation: str | None,
    left_person_type: str | None,
    right_person_type: str | None,
    left_title: str | None = None,
    right_title: str | None = None,
) -> bool:
    """Whether the rest of the two records agree enough to show this variant pair to a reviewer."""
    if affiliations_agree(left_affiliation, right_affiliation):
        return True
    if kind in ("dropped_middle", "compound_surname"):
        return False
    if not affiliations_both_absent(left_affiliation, right_affiliation):
        return False
    if kind == "spelling" and _same_title(left_title, right_title):
        return True
    return left_person_type == right_person_type


def _same_title(left: str | None, right: str | None) -> bool:
    folded = _fold(left).strip()
    return bool(folded) and folded == _fold(right).strip()
