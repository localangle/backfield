"""Abbreviation-aware sentence boundary helpers for news text."""

from __future__ import annotations

import re

# Same width as "." so protected text keeps character offsets aligned with the source.
PROTECTED_PERIOD = "\u2024"

# Titles, places, streets, orgs, dates, and other tokens that commonly appear in
# local-news copy with a non-boundary period. Keep entries with their trailing ".".
SENTENCE_ABBREVIATIONS: tuple[str, ...] = (
    "Mr.",
    "Mrs.",
    "Ms.",
    "Mx.",
    "Dr.",
    "Prof.",
    "Rev.",
    "Hon.",
    "Fr.",
    "Sr.",
    "Jr.",
    "St.",
    "Mt.",
    "Ft.",
    "Lt.",
    "Gen.",
    "Col.",
    "Maj.",
    "Capt.",
    "Cmdr.",
    "Sgt.",
    "Cpl.",
    "Pvt.",
    "Det.",
    "Ofc.",
    "Sen.",
    "Rep.",
    "Gov.",
    "Pres.",
    "Atty.",
    "Ald.",
    "Supt.",
    "Comm.",
    "Ave.",
    "Blvd.",
    "Pkwy.",
    "Hwy.",
    "Rd.",
    "Ln.",
    "Ct.",
    "Cir.",
    "Pl.",
    "Sq.",
    "Ter.",
    "Trl.",
    "Bldg.",
    "Apt.",
    "Ste.",
    "Dept.",
    "Dist.",
    "Assn.",
    "Univ.",
    "Inc.",
    "Ltd.",
    "Corp.",
    "Co.",
    "Bros.",
    "No.",
    "Fig.",
    "Vol.",
    "pp.",
    "vs.",
    "etc.",
    "approx.",
    "ca.",
    "Jan.",
    "Feb.",
    "Mar.",
    "Apr.",
    "Jun.",
    "Jul.",
    "Aug.",
    "Sep.",
    "Sept.",
    "Oct.",
    "Nov.",
    "Dec.",
    "Mon.",
    "Tue.",
    "Tues.",
    "Wed.",
    "Thu.",
    "Thur.",
    "Thurs.",
    "Fri.",
    "Sat.",
    "Sun.",
    "U.S.",
    "U.K.",
    "U.N.",
    "E.U.",
    "D.C.",
    "a.m.",
    "p.m.",
    "A.M.",
    "P.M.",
)

# Single-letter initials / dotted acronyms (J.B., U.S.) without eating "ended."
_SINGLE_LETTER_PERIOD_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]\.")

# Period/question/exclamation, optional closing quotes/parens, whitespace, then
# a likely new-sentence starter (capital, digit, or opening quote/paren/bracket).
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?])(?:[\"”’)\]]*)\s+(?=[A-Z0-9“\"'(\[])"
)

# "10 a.m. Next sentence" — the period after m is both abbreviation and boundary.
_TIME_ABBREV_SENTENCE_BOUNDARY_RE = re.compile(
    rf"(?i)(?<![A-Za-z])([ap]){re.escape(PROTECTED_PERIOD)}"
    rf"(m){re.escape(PROTECTED_PERIOD)}(\s+)(?=[A-Z0-9“\"'(\[])"
)

_SPACE_RE = re.compile(r"\s+")


def protect_abbreviation_periods(text: str) -> str:
    """Replace non-boundary abbreviation periods with a same-width sentinel."""
    if not text:
        return text
    protected = _SINGLE_LETTER_PERIOD_RE.sub(
        lambda match: match.group(0)[:-1] + PROTECTED_PERIOD,
        text,
    )
    for abbreviation in SENTENCE_ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbreviation),
            abbreviation.replace(".", PROTECTED_PERIOD),
            protected,
            flags=re.IGNORECASE,
        )
    # Re-open a real period after a.m./p.m. when a new sentence clearly follows.
    return _TIME_ABBREV_SENTENCE_BOUNDARY_RE.sub(
        lambda match: (
            f"{match.group(1)}{PROTECTED_PERIOD}{match.group(2)}.{match.group(3)}"
        ),
        protected,
    )


def restore_abbreviation_periods(text: str) -> str:
    return text.replace(PROTECTED_PERIOD, ".")


def split_sentences(text: str) -> tuple[str, ...]:
    """Split ``text`` into sentences, keeping common abbreviation periods intact."""
    cleaned = _SPACE_RE.sub(" ", text.strip()) if text else ""
    if not cleaned:
        return ()
    protected = protect_abbreviation_periods(cleaned)
    return tuple(
        restore_abbreviation_periods(part).strip()
        for part in _SENTENCE_BOUNDARY_RE.split(protected)
        if part.strip()
    )


def sentence_bounds_containing(text: str, start: int, end: int) -> tuple[int, int]:
    """Return ``[sent_start, sent_end)`` covering ``text[start:end]``.

    Offsets refer to the original ``text``. Abbreviation periods do not count as
    sentence boundaries.
    """
    if not text or start < 0 or end <= start or end > len(text):
        if 0 <= start < end <= len(text):
            return start, end
        return 0, 0

    protected = protect_abbreviation_periods(text)
    sent_start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(protected[:start]):
        sent_start = match.end()

    sent_end = len(text)
    for match in _SENTENCE_BOUNDARY_RE.finditer(protected[end:]):
        # Include the sentence-ending punctuation that triggered the break.
        sent_end = end + match.start() + 1
        break

    return sent_start, sent_end


def sentence_containing(text: str, start: int, end: int) -> str:
    """Return the sentence slice of ``text`` that contains ``[start, end)``."""
    sent_start, sent_end = sentence_bounds_containing(text, start, end)
    if sent_end <= sent_start:
        return ""
    return text[sent_start:sent_end].strip()


def iter_sentence_break_matches(text: str) -> list[re.Match[str]]:
    """Return boundary matches over abbreviation-protected ``text`` (same offsets)."""
    return list(_SENTENCE_BOUNDARY_RE.finditer(protect_abbreviation_periods(text)))
