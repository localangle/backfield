"""Offset-safe matching for entity occurrence evidence in article text."""

from __future__ import annotations

import unicodedata
from bisect import bisect_left
from dataclasses import dataclass

_QUOTE_SENTINEL = "\ue000"
_TRAILING_ARTIFACTS = frozenset('.,;:!?)]}"\'…\u201d\u2019\u201c')
_SERIALIZED_WHITESPACE = ("\\u00a0", "\\xa0", "u00a0", "xa0", "a0")


@dataclass(frozen=True)
class _MappedText:
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]


def _serialized_whitespace_at(text: str, index: int) -> int:
    for artifact in _SERIALIZED_WHITESPACE:
        end = index + len(artifact)
        if text[index:end].lower() != artifact:
            continue
        if artifact == "a0" and (
            index == 0
            or end == len(text)
            or not text[index - 1].isalnum()
            or not text[end].isalnum()
        ):
            continue
        return len(artifact)
    return 0


def _canonical_character(character: str) -> str:
    codepoint = ord(character)
    if character in {'"', "'", "`"}:
        return _QUOTE_SENTINEL
    if 0x2010 <= codepoint <= 0x2015 or character == "\u2212":
        return "-"
    if character in "\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f\u00ab\u00bb\u2032\u2033":
        return _QUOTE_SENTINEL
    return character


def _append_space(
    normalized: list[str],
    starts: list[int],
    ends: list[int],
    *,
    start: int,
    end: int,
) -> None:
    if normalized and normalized[-1] == " ":
        ends[-1] = end
        return
    normalized.append(" ")
    starts.append(start)
    ends.append(end)


def _normalize_with_offsets(text: str) -> _MappedText:
    normalized: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    index = 0

    while index < len(text):
        artifact_length = _serialized_whitespace_at(text, index)
        if artifact_length:
            _append_space(
                normalized,
                starts,
                ends,
                start=index,
                end=index + artifact_length,
            )
            index += artifact_length
            continue

        if text[index].isspace():
            end = index + 1
            while end < len(text):
                next_artifact_length = _serialized_whitespace_at(text, end)
                if next_artifact_length:
                    end += next_artifact_length
                elif text[end].isspace():
                    end += 1
                else:
                    break
            _append_space(normalized, starts, ends, start=index, end=end)
            index = end
            continue

        end = index + 1
        while end < len(text) and unicodedata.combining(text[end]):
            end += 1
        normalized_unit = unicodedata.normalize("NFKC", text[index:end])
        for character in normalized_unit:
            normalized.append(_canonical_character(character))
            starts.append(index)
            ends.append(end)
        index = end

    left = 0
    right = len(normalized)
    while left < right and normalized[left] == " ":
        left += 1
    while right > left and normalized[right - 1] == " ":
        right -= 1
    return _MappedText(
        text="".join(normalized[left:right]),
        starts=tuple(starts[left:right]),
        ends=tuple(ends[left:right]),
    )


def _evidence_variants(evidence: str) -> tuple[str, ...]:
    stripped = evidence.strip()
    without_trailing_artifacts = stripped
    while without_trailing_artifacts and without_trailing_artifacts[-1] in _TRAILING_ARTIFACTS:
        without_trailing_artifacts = without_trailing_artifacts[:-1].rstrip()
    if without_trailing_artifacts and without_trailing_artifacts != stripped:
        return stripped, without_trailing_artifacts
    return (stripped,) if stripped else ()


def _normalized_evidence(evidence_texts: tuple[str | None, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for evidence in evidence_texts:
        if not evidence:
            continue
        for variant in _evidence_variants(evidence):
            candidate = _normalize_with_offsets(variant).text
            if candidate and candidate not in normalized:
                normalized.append(candidate)
    return tuple(normalized)


def _slice_matches_evidence(
    article_text: str,
    *,
    span: tuple[int, int],
    normalized_evidence: tuple[str, ...],
) -> bool:
    start, end = span
    if start < 0 or end < start or end > len(article_text):
        return False
    normalized_slice = _normalize_with_offsets(article_text[start:end]).text
    return normalized_slice in normalized_evidence


def find_proven_occurrence_span(
    *,
    article_text: str,
    evidence_texts: tuple[str | None, ...],
    search_from: int = 0,
    proposed_span: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Return offsets only when the article slice is normalization-equivalent evidence."""

    normalized_evidence = _normalized_evidence(evidence_texts)
    if not normalized_evidence:
        return None

    if proposed_span is not None and _slice_matches_evidence(
        article_text,
        span=proposed_span,
        normalized_evidence=normalized_evidence,
    ):
        return proposed_span

    mapped_article = _normalize_with_offsets(article_text)
    if not mapped_article.text:
        return None

    normalized_start = bisect_left(mapped_article.starts, max(0, search_from))
    for evidence in normalized_evidence:
        match_index = mapped_article.text.find(evidence, normalized_start)
        while match_index >= 0:
            span = (
                mapped_article.starts[match_index],
                mapped_article.ends[match_index + len(evidence) - 1],
            )
            if _slice_matches_evidence(
                article_text,
                span=span,
                normalized_evidence=(evidence,),
            ):
                return span
            match_index = mapped_article.text.find(evidence, match_index + 1)
    return None
