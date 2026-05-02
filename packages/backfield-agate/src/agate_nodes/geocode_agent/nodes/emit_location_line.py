"""LLM-backed ``location`` display line for consolidated geocode output (with heuristic fallback)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import string
from pathlib import Path

from agate_utils.llm import call_llm

from ..types import AgentState

logger = logging.getLogger(__name__)

_CONTEXT_SNIPPET_MAX = 1200
_HINTS_SNIPPET_MAX = 800

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "location_display_format.md"
_POLISH_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "polish_location_display.md"

_TRAIL_US = re.compile(
    r",\s*(US|USA|United States)\s*$",
    re.IGNORECASE,
)

# ISO 3166-2-style alpha-2 codes for US subdivisions (50 + DC) and Canadian provinces/territories.
# Used only to normalize a lone trailing comma segment that is exactly two letters (root fix for casing).
_SUBNATIONAL_2: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        # Canada
        "AB",
        "BC",
        "MB",
        "NB",
        "NL",
        "NS",
        "NT",
        "NU",
        "ON",
        "PE",
        "QC",
        "SK",
        "YT",
    }
)

# Lowercase inside a segment when not the first word (Chicago-style / publication titles).
_SMALL_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "nor",
        "of",
        "on",
        "or",
        "so",
        "the",
        "to",
        "via",
        "yet",
    }
)

# Skip Irish/French-style apostrophe “fix” when this looks like an English contraction.
_CONTRACTION_SUFFIX = re.compile(r"(n't|'t|'s|'re|'ve|'ll|'m)$", re.IGNORECASE)

# Dotted initialisms: ``U.S.``, ``D.C.``, ``N.Y.``, ``U.S.A.`` (``string.capwords`` yields ``U.s.``).
_DOTTED_INITIALISM = re.compile(r"^(?:[A-Za-z]\.)+[A-Za-z]?\.?$")
# ``Ph.d.`` / ``Sc.d.``-style: multi-letter stem + dot + single letter (+ optional dot).
_LETTER_DOT_SINGLE_LETTER = re.compile(r"^([A-Za-z]{2,})\.([A-Za-z])(\.?)$")
# Short ``AT&T`` / ``H&R``-style tokens (``capwords`` can yield ``At&t``).
_AMPERSAND_ACRONYM = re.compile(r"^([A-Za-z]{1,4})&([A-Za-z]{1,4})$", re.IGNORECASE)

# Keep common Latin abbreviations out of the all-caps dotted rule.
_LATIN_ABBREV_CF = frozenset({"e.g.", "i.e.", "a.m.", "p.m."})


def _letters_to_upper_for_acronym(token: str) -> str:
    return "".join(ch.upper() if ch.isalpha() else ch for ch in token)


def _promote_token_acronym_casing(token: str) -> str:
    """
    Restore acronym casing after ``string.capwords`` (e.g. ``U.s.`` → ``U.S.``, ``Ph.d.`` → ``Ph.D.``).
    """
    if not token:
        return token
    if token.casefold() in _LATIN_ABBREV_CF:
        return token
    if _DOTTED_INITIALISM.fullmatch(token):
        return _letters_to_upper_for_acronym(token)
    m = _LETTER_DOT_SINGLE_LETTER.fullmatch(token)
    if m:
        left, letter, tail = m.group(1), m.group(2), m.group(3)
        return f"{left[0].upper()}{left[1:].lower()}.{letter.upper()}{tail}"
    m2 = _AMPERSAND_ACRONYM.fullmatch(token)
    if m2:
        return f"{m2.group(1).upper()}&{m2.group(2).upper()}"
    return token


def _promote_acronyms_in_segment(seg: str) -> str:
    if not (seg or "").strip():
        return seg
    return " ".join(_promote_token_acronym_casing(part) for part in seg.split())


def _title_segment_words(seg: str) -> str:
    """Title-case words in one segment; preserve hyphenated names."""
    seg = seg.strip()
    if not seg:
        return seg
    if "-" in seg:
        return "-".join(_title_segment_words(part) for part in seg.split("-"))
    capped = string.capwords(seg)
    return _promote_acronyms_in_segment(capped)


def apply_title_case_location_line(line: str) -> str:
    """
    Title-case place names by comma segment; uppercase US/CA 2-letter subdivision codes.

    Trailing ``US`` (country) after a comma is kept as uppercase ``US``.
    """
    s = (line or "").strip()
    if not s:
        return s
    raw_parts = [p.strip() for p in s.split(",")]
    parts: list[str] = [p for p in raw_parts if p]
    if not parts:
        return s
    out: list[str] = []
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        if re.fullmatch(r"[A-Za-z]{2}", part) and part.upper() in _SUBNATIONAL_2:
            out.append(part.upper())
        elif is_last and part.upper() == "US":
            out.append("US")
        else:
            out.append(_title_segment_words(part))
    return ", ".join(out)


# Standalone comma segments that are geographic *types*, not toponyms (geocoder/LLM noise).
_STANDALONE_TYPE_SEGMENTS: frozenset[str] = frozenset({"neighborhood", "district"})


def _strip_standalone_placetype_label_segments(line: str) -> str:
    """Remove comma segments that are only a generic placetype word (e.g. ``Neighborhood``)."""
    parts = [p.strip() for p in line.split(",") if p.strip()]
    if not parts:
        return (line or "").strip()
    kept = [p for p in parts if p.casefold() not in _STANDALONE_TYPE_SEGMENTS]
    if not kept:
        return ", ".join(parts)
    return ", ".join(kept)


def _collapse_duplicate_consecutive_segments(line: str) -> str:
    """Drop consecutive comma segments that are the same toponym (case-insensitive)."""
    parts = [p.strip() for p in line.split(",") if p.strip()]
    if len(parts) < 2:
        return (line or "").strip()
    out: list[str] = [parts[0]]
    for p in parts[1:]:
        if p.casefold() == out[-1].casefold():
            continue
        out.append(p)
    return ", ".join(out)


def _lowercase_small_word_token(word: str, word_index: int) -> str:
    """Lowercase a joiner word when not the first token in a comma segment."""
    m = re.match(r"^(\W*)(\w+)(\W*)$", word)
    if not m:
        return word
    lead, core, trail = m.group(1), m.group(2), m.group(3)
    if word_index > 0 and core.lower() in _SMALL_WORDS:
        return f"{lead}{core.lower()}{trail}"
    return word


def _lowercase_small_words(line: str) -> str:
    """Lowercase joiners (of, and, …) except the first word of each comma segment."""
    segments: list[str] = []
    for seg in line.split(","):
        seg = seg.strip()
        if not seg:
            continue
        words = seg.split()
        if not words:
            segments.append(seg)
            continue
        next_words = [_lowercase_small_word_token(w, wi) for wi, w in enumerate(words)]
        segments.append(" ".join(next_words))
    return ", ".join(segments)


def _fix_apostrophe_leading_name_word(word: str) -> str:
    """``Letter'Name`` pattern: capitalize after apostrophe; skip English contractions."""
    if word.count("'") != 1 or _CONTRACTION_SUFFIX.search(word):
        return word
    m = re.match(r"^(\W*)([A-Za-z])'([a-z]{3,})(\W*)$", word)
    if not m:
        return word
    lead, letter, rest, trail = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"{lead}{letter.upper()}'{rest[0].upper()}{rest[1:]}{trail}"


def _fix_apostrophe_names_line(line: str) -> str:
    out_parts: list[str] = []
    for seg in line.split(","):
        seg = seg.strip()
        if not seg:
            continue
        words = [_fix_apostrophe_leading_name_word(w) for w in seg.split()]
        out_parts.append(" ".join(words))
    return ", ".join(out_parts)


def refine_location_display_line(line: str) -> str:
    """
    Deterministic refinements: title case + NA subdivision codes, dedupe segments, small words,
    apostrophe names.
    """
    s = (line or "").strip()
    if not s:
        return s
    s = apply_title_case_location_line(s)
    s = _collapse_duplicate_consecutive_segments(s)
    s = _strip_standalone_placetype_label_segments(s)
    s = _lowercase_small_words(s)
    s = _fix_apostrophe_names_line(s)
    return s


def _story_context_snippets(state: AgentState) -> tuple[str, str]:
    """Truncate article text and geocode hints for LLM prompts (token control)."""
    orig = (state.get("original_text") or "").strip()
    if not orig:
        orig_snip = "(none)"
    elif len(orig) > _CONTEXT_SNIPPET_MAX:
        orig_snip = orig[:_CONTEXT_SNIPPET_MAX] + "…"
    else:
        orig_snip = orig
    hints_raw = (state.get("geocode_hints") or "").strip()
    if not hints_raw:
        hints_snip = "(none)"
    elif len(hints_raw) > _HINTS_SNIPPET_MAX:
        hints_snip = hints_raw[:_HINTS_SNIPPET_MAX] + "…"
    else:
        hints_snip = hints_raw
    return orig_snip, hints_snip


def _heuristic_emit_location(
    location_type: str,
    location_text: str,
    formatted_address: str,
) -> str:
    """Cheap fallback when LLM is skipped or fails."""
    lt = (location_type or "").lower()
    base = (location_text or "").strip() or (formatted_address or "").strip()
    out = base
    if lt != "region_country" and out:
        out = _TRAIL_US.sub("", out).rstrip().rstrip(",").strip()
    if lt == "region_country" and out:
        out = re.sub(r"\bUSA\b", "US", out)
    return refine_location_display_line(out)


async def _maybe_polish_with_llm(
    candidate: str,
    model: str,
    openai_key: str,
    *,
    story_context: str = "(none)",
    geocode_hints: str = "(none)",
) -> str:
    """Optional final LLM pass for edge cases; deterministic pass reapplied after."""
    cand = (candidate or "").strip()
    if not cand:
        return cand
    try:
        template = _POLISH_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("polish_location_display prompt missing: %s", exc)
        return candidate
    sc = (story_context or "").strip() or "(none)"
    gh = (geocode_hints or "").strip() or "(none)"
    prompt = (
        template.replace("{candidate}", cand)
        .replace("{story_context}", sc)
        .replace("{geocode_hints}", gh)
    )

    def _sync() -> str:
        return call_llm(
            prompt,
            model,
            None,
            True,
            1,
            0.0,
            512,
            openai_key,
            None,
            None,
            45.0,
        )

    try:
        raw = await asyncio.to_thread(_sync)
        payload = json.loads(raw)
    except Exception as exc:
        logger.debug("polish_location_display LLM failed: %s", exc)
        return candidate

    loc = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(loc, str):
        return candidate
    loc = loc.strip()
    if not loc:
        return candidate
    return refine_location_display_line(loc)


async def compute_emit_location_line(
    state: AgentState,
    *,
    formatted_address: str,
) -> str:
    """
    Produce the human-facing ``location`` string for a geocoded item.

    Uses a small JSON LLM when ``openai_api_key`` is set; otherwise heuristics on ``location_text``.
    """
    location_type = (state.get("location_type") or "").strip()
    location_text = (state.get("location_text") or "").strip()
    formatted_address = (formatted_address or "").strip()
    openai_key = state.get("openai_api_key")
    model = (
        state.get("evaluation_llm_model")
        or state.get("router_llm_model")
        or "gpt-5-nano"
    )
    polish_model = state.get("evaluation_llm_model") or state.get("router_llm_model") or "gpt-5-nano"
    components = state.get("location_components") or {}
    if not isinstance(components, dict):
        components = {}
    components_json = json.dumps(components, default=str, ensure_ascii=False)[:2000]
    orig_snip, hints_snip = _story_context_snippets(state)

    if not openai_key:
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    try:
        rules = _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("location_display_format prompt missing: %s", exc)
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    user_block = (
        f"type: {location_type}\n"
        f"q: {location_text}\n"
        f"formatted_address: {formatted_address}\n"
        f"components_json: {components_json}\n"
        f"original_text: {orig_snip}\n"
        f"geocode_hints: {hints_snip}\n"
    )
    prompt = f"{rules}\n---\n{user_block}"

    def _sync() -> str:
        return call_llm(
            prompt,
            model,
            None,
            True,
            1,
            0.0,
            512,
            openai_key,
            None,
            None,
            45.0,
        )

    try:
        raw = await asyncio.to_thread(_sync)
        payload = json.loads(raw)
    except Exception as exc:
        logger.debug("emit_location_line LLM failed, using heuristic: %s", exc)
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    loc = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(loc, str):
        return _heuristic_emit_location(location_type, location_text, formatted_address)
    loc = loc.strip()
    if not loc:
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    refined = refine_location_display_line(loc)
    return await _maybe_polish_with_llm(
        refined,
        polish_model,
        openai_key,
        story_context=orig_snip,
        geocode_hints=hints_snip,
    )
