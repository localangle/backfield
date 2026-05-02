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


def _title_segment_words(seg: str) -> str:
    """Title-case words in one segment; preserve hyphenated names."""
    seg = seg.strip()
    if not seg:
        return seg
    if "-" in seg:
        return "-".join(_title_segment_words(part) for part in seg.split("-"))
    return string.capwords(seg)


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
    s = _lowercase_small_words(s)
    s = _fix_apostrophe_names_line(s)
    return s


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


async def _maybe_polish_with_llm(candidate: str, model: str, openai_key: str) -> str:
    """Optional final LLM pass for edge cases; deterministic pass reapplied after."""
    cand = (candidate or "").strip()
    if not cand:
        return cand
    try:
        template = _POLISH_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("polish_location_display prompt missing: %s", exc)
        return candidate
    prompt = template.replace("{candidate}", cand)

    def _sync() -> str:
        return call_llm(
            prompt,
            model,
            None,
            True,
            1,
            0.0,
            384,
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
    return await _maybe_polish_with_llm(refined, polish_model, openai_key)
