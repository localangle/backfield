"""Deterministic PlaceExtract mention reconstruction for compact expansion."""

from __future__ import annotations

import re
from typing import Any

from agate_nodes.place_extract.location_utils import split_location_parts
from agate_nodes.place_extract.schedule_matchups import find_schedule_line_for_school

MAX_MENTIONS_PER_LOCATION = 8
_PRIMARY_NEEDLE_BOUNDARY_MAX_LEN = 20

_WS_RE = re.compile(r"\s+")
_SPAN_QUOTE_SENTINEL = "\ue000"
_TRAILING_SPAN_ARTIFACT_CHARS = frozenset(
    '.,;:!?)]}"\'…\u201d\u2019\u201c'
)
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+")


def _rstrip_trailing_span_artifacts(fragment: str) -> str:
    cleaned = fragment.rstrip()
    while cleaned and cleaned[-1] in _TRAILING_SPAN_ARTIFACT_CHARS:
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _mention_text_span_variants(needle: str) -> list[str]:
    stripped = _rstrip_trailing_span_artifacts(needle)
    if stripped == needle:
        return [needle] if needle else []
    out: list[str] = []
    if needle:
        out.append(needle)
    if stripped:
        out.append(stripped)
    return out


def _normalize_quotes_for_span_match(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch in {'"', "'", "`"}:
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch == "\u00a0":
            out.append(" ")
        elif 0x2010 <= code <= 0x2015 or ch == "\u2212":
            out.append("-")
        elif ch in "\u2018\u2019\u201a\u201b":
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u201c\u201d\u201e\u201f":
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u00ab\u00bb":
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u2032\u2033":
            out.append(_SPAN_QUOTE_SENTINEL)
        else:
            out.append(ch)
    return "".join(out)


def _longest_needle_substring_span(
    *,
    haystack: str,
    needle: str,
    min_len: int = 12,
) -> tuple[int, int] | None:
    if not needle or len(needle) < min_len:
        return None

    hay_n = _normalize_quotes_for_span_match(haystack)
    need_n = _normalize_quotes_for_span_match(needle)
    if len(need_n) < min_len:
        return None

    best: tuple[int, int] | None = None
    best_len = 0
    for start in range(len(need_n)):
        for end in range(len(need_n), start, -1):
            fragment = need_n[start:end]
            span_len = end - start
            if span_len < min_len or span_len <= best_len:
                continue
            idx = hay_n.find(fragment)
            if idx >= 0:
                best_len = span_len
                best = (idx, idx + span_len)
                break
    return best


def _matches_at(haystack: str, needle: str, index: int, *, require_word_boundary: bool) -> bool:
    if haystack[index : index + len(needle)] != needle:
        return False
    if not require_word_boundary:
        return True
    before_ok = index == 0 or not haystack[index - 1].isalnum()
    end = index + len(needle)
    after_ok = end >= len(haystack) or not haystack[end].isalnum()
    return before_ok and after_ok


def find_mention_span(
    haystack: str,
    needle: str,
    search_from: int = 0,
    *,
    require_word_boundary: bool = False,
) -> tuple[int, int] | None:
    if not needle:
        return None
    if search_from < 0:
        search_from = 0
    if search_from >= len(haystack):
        return None

    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        idx = haystack.find(candidate, search_from)
        while idx >= 0:
            if _matches_at(haystack, candidate, idx, require_word_boundary=require_word_boundary):
                return idx, idx + len(candidate)
            idx = haystack.find(candidate, idx + 1)

    hay_q = _normalize_quotes_for_span_match(haystack)
    hay_q_slice = hay_q[search_from:]
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        cand_q = _normalize_quotes_for_span_match(candidate)
        idx = hay_q_slice.find(cand_q)
        if idx >= 0:
            return search_from + idx, search_from + idx + len(candidate)

    collapsed_hay = _WS_RE.sub(" ", haystack).strip()
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        collapsed_needle = _WS_RE.sub(" ", candidate).strip()
        if not collapsed_needle:
            continue
        if collapsed_hay.find(collapsed_needle) >= 0:
            first_token = collapsed_needle.split(" ")[0]
            if first_token:
                idx3 = haystack.find(first_token, search_from)
                if idx3 >= 0:
                    return idx3, idx3 + len(candidate)

    for candidate in _mention_text_span_variants(needle):
        span = _longest_needle_substring_span(haystack=haystack[search_from:], needle=candidate)
        if span is not None:
            return search_from + span[0], search_from + span[1]

    return None


def find_all_mention_spans(
    haystack: str,
    needle: str,
    *,
    search_from: int = 0,
    require_word_boundary: bool = False,
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    cursor = search_from
    while cursor < len(haystack):
        span = find_mention_span(
            haystack,
            needle,
            cursor,
            require_word_boundary=require_word_boundary,
        )
        if span is None:
            break
        if span not in seen:
            seen.add(span)
            spans.append(span)
        cursor = max(cursor + 1, span[1])

    if needle and re.search(r"[A-Za-z]", needle) and not require_word_boundary:
        pattern = re.compile(re.escape(needle), flags=re.IGNORECASE)
        for match in pattern.finditer(haystack, search_from):
            span = (match.start(), match.end())
            if span not in seen:
                seen.add(span)
                spans.append(span)

    spans.sort(key=lambda item: item[0])
    return spans


def sentence_containing_span(text: str, start: int, end: int) -> str:
    """Return the sentence (or clause block) that contains ``text[start:end]``."""
    if not text or start < 0 or end <= start or end > len(text):
        return text[start:end].strip() if 0 <= start < end <= len(text) else ""

    sent_start = 0
    for match in _SENTENCE_BREAK_RE.finditer(text[:start]):
        sent_start = match.end()

    sent_end = len(text)
    for match in _SENTENCE_BREAK_RE.finditer(text[end:]):
        sent_end = end + match.start() + 1
        break

    return text[sent_start:sent_end].strip()


def mention_context_containing_span(text: str, start: int, end: int) -> str:
    """Return the best verbatim mention context: sentence when possible, else paragraph block."""
    if not text or start < 0 or end <= start or end > len(text):
        return text[start:end].strip() if 0 <= start < end <= len(text) else ""

    para_start = text.rfind("\n\n", 0, start)
    para_start = para_start + 2 if para_start >= 0 else 0
    para_end = text.find("\n\n", end)
    para_end = para_end if para_end >= 0 else len(text)
    paragraph = text[para_start:para_end].strip()
    if not paragraph:
        return text[start:end].strip()

    rel_start = max(0, start - para_start)
    rel_end = min(len(paragraph), end - para_start)
    sentence = sentence_containing_span(paragraph, rel_start, rel_end).strip()
    if sentence and len(sentence) < len(paragraph):
        return sentence
    return paragraph


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


def _needle_case_variants(text: str) -> list[str]:
    variants = [text]
    if text != text.upper():
        variants.append(text.upper())
    if text != text.title() and text.title() != text.upper():
        variants.append(text.title())
    return variants


def mention_needles(
    location: str,
    location_type: str,
    article_text: str = "",
) -> list[tuple[str, bool]]:
    """Search phrases and whether each requires word-boundary matching."""
    parts = split_location_parts(location)
    primary = parts[0] if parts else location.strip()
    full_location = location.strip()
    needles: list[tuple[str, bool]] = [(full_location, False)]

    if primary and primary != full_location:
        require_boundary = len(primary) < _PRIMARY_NEEDLE_BOUNDARY_MAX_LEN
        needles.append((primary, require_boundary))

    if location_type in {"state", "country", "region_national"}:
        for variant in _needle_case_variants(primary):
            needles.append((variant, len(variant) < _PRIMARY_NEEDLE_BOUNDARY_MAX_LEN))
    elif location_type == "city":
        if len(parts) >= 2 and parts[-1]:
            needles.append((f"{primary}, {parts[-1]}", False))
        for variant in _needle_case_variants(primary):
            needles.append((variant, len(variant) < _PRIMARY_NEEDLE_BOUNDARY_MAX_LEN))
    elif location_type in {"intersection_road", "intersection_highway"}:
        if re.search(r"\s+and\s+", primary, flags=re.IGNORECASE):
            for side in re.split(r"\s+and\s+", primary, flags=re.IGNORECASE):
                side = side.strip()
                if side:
                    needles.append((side, len(side) < _PRIMARY_NEEDLE_BOUNDARY_MAX_LEN))
    elif location_type == "place" and article_text:
        for side in (primary, full_location.split(",")[0].strip()):
            schedule_line = find_schedule_line_for_school(article_text, side)
            if schedule_line:
                needles.insert(0, (schedule_line, False))

    deduped: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for needle, require_boundary in needles:
        key = needle.strip().lower()
        if not key or key in seen or len(needle.strip()) < 2:
            continue
        seen.add(key)
        deduped.append((needle.strip(), require_boundary))
    deduped.sort(key=lambda item: len(item[0]), reverse=True)
    return deduped


def _mention_records_for_spans(article_text: str, spans: list[tuple[int, int]]) -> list[dict[str, str]]:
    mentions: list[dict[str, str]] = []
    seen_sentences: set[str] = set()
    for start, end in spans:
        text = mention_context_containing_span(article_text, start, end)
        if not text:
            text = article_text[start:end].strip()
        key = text.strip().lower()
        if not key or key in seen_sentences:
            continue
        seen_sentences.add(key)
        mentions.append({"text": text})
        if len(mentions) >= MAX_MENTIONS_PER_LOCATION:
            break
    return mentions


def build_mentions(article_text: str, location: str, location_type: str) -> list[dict[str, str]]:
    """Reconstruct ``[{text}]`` mentions by locating the place in the article."""
    spans: list[tuple[int, int]] = []
    seen_spans: set[tuple[int, int]] = set()
    for needle, require_boundary in mention_needles(location, location_type, article_text):
        for span in find_all_mention_spans(
            article_text,
            needle,
            require_word_boundary=require_boundary,
        ):
            if span not in seen_spans:
                seen_spans.add(span)
                spans.append(span)
    spans.sort(key=lambda item: item[0])

    mentions = _mention_records_for_spans(article_text, spans)
    if mentions:
        return mentions

    for needle, require_boundary in mention_needles(location, location_type, article_text):
        span = find_mention_span(
            article_text,
            needle,
            require_word_boundary=require_boundary,
        )
        if span is not None:
            return _mention_records_for_spans(article_text, [span])

    location = location.strip()
    if location:
        return [{"text": location}]
    return []
