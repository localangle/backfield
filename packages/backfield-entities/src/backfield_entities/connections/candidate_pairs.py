"""Evidence-first candidate pair generation for automatic connections."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from backfield_entities.connections.caps import (
    MIN_PAIR_EVIDENCE_SCORE_FOR_ENTITY_RESERVATION,
)
from backfield_entities.connections.match_tokens import (
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
    LinkedEntitySnapshot,
    PairEvidencePacket,
)
from backfield_entities.entities.organization.types import normalize_organization_text

AUTO_CONNECTION_FAMILIES: tuple[tuple[str, str], ...] = (
    ("person", "organization"),
    ("organization", "location"),
    ("person", "location"),
    ("person", "person"),
    ("organization", "organization"),
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?:[\"”’)]*)\s+(?=[A-Z0-9“\"'])")
_SPACE = re.compile(r"\s+")
_ABBREVIATIONS = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "U.S.", "No.")
_PROTECTED_PERIOD = "\u2024"
_TEAM_SUFFIXES = (
    " high school boys football team",
    " high school girls football team",
    " high school football team",
    " boys football team",
    " girls football team",
    " football team",
    " basketball team",
    " baseball team",
    " team",
)
_GENERIC_ORG_TAIL = frozenset({"team", "inc", "llc", "corp", "ltd", "co"})


@dataclass
class CandidateGenerationStats:
    considered: int = 0
    generated: int = 0
    rejected_no_evidence: int = 0
    truncated: int = 0
    by_source: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateGenerationResult:
    candidates: tuple[AutoConnectionCandidatePair, ...]
    stats: CandidateGenerationStats


def _clean(value: str) -> str:
    return _SPACE.sub(" ", value.strip())


def _aliases(entity: LinkedEntitySnapshot) -> tuple[str, ...]:
    label = _clean(entity.label)
    if not label:
        return ()
    aliases: list[str] = [label]
    lowered = label.casefold()
    if entity.entity_type == "person":
        parts = label.split()
        if len(parts) > 1 and len(parts[-1]) >= 4:
            aliases.append(parts[-1])
    elif entity.entity_type == "organization":
        for suffix in _TEAM_SUFFIXES:
            if lowered.endswith(suffix):
                head = label[: -len(suffix)].strip()
                if len(head) >= 4:
                    aliases.append(head)
                break
        parts = label.split()
        if len(parts) > 1:
            tail = parts[-1]
            if len(tail) >= 3 and tail.casefold() not in _GENERIC_ORG_TAIL:
                aliases.append(tail)
    elif entity.entity_type == "location" and "," in label:
        head = label.split(",", 1)[0].strip()
        if len(head) >= 4:
            aliases.append(head)
    out: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = alias.casefold()
        if key not in seen:
            seen.add(key)
            out.append(alias)
    return tuple(out)


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(alias.casefold() in lowered for alias in aliases)


def _sentences(article_text: str) -> tuple[str, ...]:
    text = _clean(article_text)
    if not text:
        return ()
    protected = text
    for abbreviation in _ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbreviation),
            abbreviation.replace(".", _PROTECTED_PERIOD),
            protected,
            flags=re.IGNORECASE,
        )
    return tuple(
        part.replace(_PROTECTED_PERIOD, ".").strip()
        for part in _SENTENCE_BOUNDARY.split(protected)
        if part.strip()
    )


def _snippet_sentence_indexes(
    snippets: tuple[str, ...],
    article_sentences: tuple[str, ...],
) -> list[tuple[int, str]]:
    indexed: list[tuple[int, str]] = []
    for snippet in snippets:
        text = _clean(snippet).removesuffix("...")
        if not text:
            continue
        probe = text[: min(80, len(text))].casefold()
        for index, sentence in enumerate(article_sentences):
            if probe in sentence.casefold() or sentence.casefold() in text.casefold():
                indexed.append((index, text))
                break
    return indexed


def _linked_occurrence_evidence(
    left: LinkedEntitySnapshot,
    right: LinkedEntitySnapshot,
    article_sentences: tuple[str, ...],
) -> tuple[tuple[str, ...], str | None, int]:
    left_occurrences = _snippet_sentence_indexes(left.snippets, article_sentences)
    right_occurrences = _snippet_sentence_indexes(right.snippets, article_sentences)
    evidence: list[str] = []
    source: str | None = None
    score = 0
    for left_index, left_text in left_occurrences:
        for right_index, right_text in right_occurrences:
            distance = abs(left_index - right_index)
            if distance > 1:
                continue
            if distance == 0:
                quote = article_sentences[left_index]
                candidate_source = "linked_same_sentence"
                candidate_score = 40
            else:
                first = min(left_index, right_index)
                quote = f"{article_sentences[first]} {article_sentences[first + 1]}"
                candidate_source = "linked_adjacent_sentence"
                candidate_score = 30
            _ = left_text, right_text
            if quote not in evidence:
                evidence.append(quote)
            if candidate_score > score:
                source = candidate_source
                score = candidate_score
    return tuple(evidence[:4]), source, score


def _pair_text_evidence(
    left: LinkedEntitySnapshot,
    right: LinkedEntitySnapshot,
    article_sentences: tuple[str, ...],
) -> tuple[tuple[str, ...], str | None, int]:
    left_aliases = _aliases(left)
    right_aliases = _aliases(right)
    if not left_aliases or not right_aliases:
        return (), None, 0

    evidence: list[str] = []
    seen: set[str] = set()
    same_sentence = False
    adjacent_sentence = False

    for index, sentence in enumerate(article_sentences):
        has_left = _contains_alias(sentence, left_aliases)
        has_right = _contains_alias(sentence, right_aliases)
        if has_left and has_right:
            if sentence not in seen:
                seen.add(sentence)
                evidence.append(sentence)
            same_sentence = True
            continue
        if not has_left:
            continue
        for neighbor_index in (index - 1, index + 1):
            if neighbor_index < 0 or neighbor_index >= len(article_sentences):
                continue
            neighbor = article_sentences[neighbor_index]
            if not _contains_alias(neighbor, right_aliases):
                continue
            combined = (
                f"{sentence} {neighbor}"
                if neighbor_index > index
                else f"{neighbor} {sentence}"
            )
            if combined not in seen:
                seen.add(combined)
                evidence.append(combined)
            adjacent_sentence = True

    for snippet in (*left.snippets, *right.snippets):
        text = _clean(snippet)
        if (
            text
            and _contains_alias(text, left_aliases)
            and _contains_alias(text, right_aliases)
            and text not in seen
        ):
            seen.add(text)
            evidence.append(text)
            same_sentence = True

    if same_sentence:
        return tuple(evidence[:4]), "same_sentence", 40
    if adjacent_sentence:
        return tuple(evidence[:4]), "adjacent_sentence", 30
    linked_evidence = _linked_occurrence_evidence(left, right, article_sentences)
    if linked_evidence[0]:
        return linked_evidence
    return (), None, 0


def _affiliation_hint(
    left: LinkedEntitySnapshot,
    right: LinkedEntitySnapshot,
) -> str | None:
    if left.entity_type != "person" or right.entity_type != "organization":
        return None
    affiliation = (left.affiliation or "").strip()
    if not affiliation:
        return None
    if person_affiliation_matches_organization_label(affiliation, right.label):
        return f"Extracted affiliation {affiliation!r} may refer to {right.label!r}."
    aff = normalize_organization_text(affiliation)
    org = normalize_organization_text(right.label)
    if len(aff) >= 4 and org.startswith(f"{aff} "):
        return f"Extracted affiliation {affiliation!r} is a prefix of {right.label!r}."
    return None


def _metadata_evidence(
    left: LinkedEntitySnapshot,
    right: LinkedEntitySnapshot,
    hint: str,
) -> tuple[str, ...]:
    """Return article excerpts for interpretation; the hint itself is not proof."""
    snippets: list[str] = []
    seen: set[str] = set()
    for snippet in (*left.snippets, *right.snippets):
        text = _clean(snippet)
        if text and text not in seen:
            seen.add(text)
            snippets.append(text)
    _ = hint
    return tuple(snippets[:4])


def _candidate_id(left: LinkedEntitySnapshot, right: LinkedEntitySnapshot) -> str:
    raw = (
        f"{left.entity_type}:{left.canonical_id}->"
        f"{right.entity_type}:{right.canonical_id}"
    )
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"candidate-{digest}"


def _party_district_place_pattern(location: LinkedEntitySnapshot) -> str | None:
    """Regex alternation for place names used after journalistic D-/R- tags."""
    heads = [
        alias
        for alias in _aliases(location)
        if "," not in alias and len(alias) >= 3
    ]
    if not heads:
        label = _clean(location.label)
        if len(label) >= 3:
            heads = [label]
    heads = sorted(set(heads), key=len, reverse=True)
    if not heads:
        return None
    return "|".join(re.escape(head) for head in heads)


def explicit_person_represents_party_district_evidence(
    candidate: AutoConnectionCandidatePair,
) -> tuple[str, str] | None:
    """Match legislator party+district styling such as ``Amy Briel, D-Ottawa``."""
    if (
        candidate.from_entity_type != "person"
        or candidate.to_entity_type != "location"
    ):
        return None
    place_pattern = _party_district_place_pattern(candidate.to_entity)
    if place_pattern is None:
        return None
    person_aliases = _aliases(candidate.from_entity)
    if not person_aliases:
        return None
    district_pattern = re.compile(rf"\b[DR]-(?:{place_pattern})\b", re.IGNORECASE)
    for snippet in candidate.evidence.snippets:
        if not district_pattern.search(snippet):
            continue
        if not _contains_alias(snippet, person_aliases):
            continue
        return "represents", snippet
    return None


def build_deterministic_connection_proposals(
    candidates: tuple[AutoConnectionCandidatePair, ...],
) -> tuple[AutoConnectionEdgeProposal, ...]:
    """Create only high-precision journalistic-style proposals (e.g. party+district tags)."""
    proposals: list[AutoConnectionEdgeProposal] = []
    for candidate in candidates:
        matched = explicit_person_represents_party_district_evidence(candidate)
        if matched is None:
            continue
        nature, quote = matched
        proposals.append(
            AutoConnectionEdgeProposal(
                candidate_id=candidate.candidate_id,
                from_entity_id=candidate.from_entity.canonical_id,
                to_entity_id=candidate.to_entity.canonical_id,
                description=(
                    f"{candidate.from_entity.label} represents "
                    f"{candidate.to_entity.label}."
                ),
                nature=nature,
                confidence=0.99,
                quote=quote,
                reason="Journalistic party+district styling in article text.",
                match_basis="explicit_party_district_construction",
            )
        )
    return tuple(proposals)


def _best_pair_evidence_scores(
    *,
    people: tuple[LinkedEntitySnapshot, ...],
    organizations: tuple[LinkedEntitySnapshot, ...],
    locations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
) -> dict[str, int]:
    """Return the strongest textual pair-evidence score per canonical entity id."""
    by_type = {
        "person": people,
        "organization": organizations,
        "location": locations,
    }
    article_sentences = _sentences(article_text)
    best_scores: dict[str, int] = {}
    for from_type, to_type in AUTO_CONNECTION_FAMILIES:
        pairs = _family_pairs(
            by_type[from_type],
            by_type[to_type],
            same_type=from_type == to_type,
        )
        for left, right in pairs:
            snippets, _source, score = _pair_text_evidence(left, right, article_sentences)
            if not snippets or score < MIN_PAIR_EVIDENCE_SCORE_FOR_ENTITY_RESERVATION:
                continue
            for entity in (left, right):
                current = best_scores.get(entity.canonical_id, 0)
                if score > current:
                    best_scores[entity.canonical_id] = score
    return best_scores


def select_linked_entities_with_pair_priority(
    *,
    people: tuple[LinkedEntitySnapshot, ...],
    organizations: tuple[LinkedEntitySnapshot, ...],
    locations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
    limit_per_type: int,
) -> tuple[
    tuple[LinkedEntitySnapshot, ...],
    tuple[LinkedEntitySnapshot, ...],
    tuple[LinkedEntitySnapshot, ...],
]:
    """Keep occurrence-ranked entities while reserving slots for pair-evidence entities."""
    best_scores = _best_pair_evidence_scores(
        people=people,
        organizations=organizations,
        locations=locations,
        article_text=article_text,
    )

    def _select(
        entities: tuple[LinkedEntitySnapshot, ...],
    ) -> tuple[LinkedEntitySnapshot, ...]:
        if len(entities) <= limit_per_type:
            return entities
        order = {entity.canonical_id: index for index, entity in enumerate(entities)}
        reserved = [
            entity
            for entity in entities
            if best_scores.get(entity.canonical_id, 0)
            >= MIN_PAIR_EVIDENCE_SCORE_FOR_ENTITY_RESERVATION
        ]
        reserved.sort(
            key=lambda entity: (
                -best_scores.get(entity.canonical_id, 0),
                order[entity.canonical_id],
            )
        )
        reserved_ids = {entity.canonical_id for entity in reserved}
        remainder = [
            entity for entity in entities if entity.canonical_id not in reserved_ids
        ]
        return tuple((reserved + remainder)[:limit_per_type])

    return (
        _select(people),
        _select(organizations),
        _select(locations),
    )


def _family_pairs(
    left_entities: tuple[LinkedEntitySnapshot, ...],
    right_entities: tuple[LinkedEntitySnapshot, ...],
    *,
    same_type: bool,
) -> list[tuple[LinkedEntitySnapshot, LinkedEntitySnapshot]]:
    if not same_type:
        return [(left, right) for left in left_entities for right in right_entities]
    pairs: list[tuple[LinkedEntitySnapshot, LinkedEntitySnapshot]] = []
    ordered = sorted(left_entities, key=lambda entity: entity.canonical_id)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs.append((left, right))
    return pairs


def generate_connection_candidates(
    *,
    people: tuple[LinkedEntitySnapshot, ...],
    organizations: tuple[LinkedEntitySnapshot, ...],
    locations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
    limit: int,
) -> CandidateGenerationResult:
    """Generate ranked pairs with pair-scoped textual evidence."""
    by_type = {
        "person": people,
        "organization": organizations,
        "location": locations,
    }
    article_sentences = _sentences(article_text)
    candidates: list[AutoConnectionCandidatePair] = []
    stats = CandidateGenerationStats()

    for from_type, to_type in AUTO_CONNECTION_FAMILIES:
        pairs = _family_pairs(
            by_type[from_type],
            by_type[to_type],
            same_type=from_type == to_type,
        )
        for left, right in pairs:
            stats.considered += 1
            snippets, source, score = _pair_text_evidence(left, right, article_sentences)
            hint = _affiliation_hint(left, right)
            hints = (hint,) if hint else ()
            if not snippets and hint:
                snippets = _metadata_evidence(left, right, hint)
                source = "metadata_hint"
                score = 10
            if not snippets or source is None:
                stats.rejected_no_evidence += 1
                continue
            packet = PairEvidencePacket(
                snippets=snippets,
                source=source,
                score=score,
                match_basis=source,
                hints=hints,
            )
            candidates.append(
                AutoConnectionCandidatePair(
                    candidate_id=_candidate_id(left, right),
                    from_entity=left,
                    to_entity=right,
                    evidence=packet,
                )
            )
            stats.by_source[source] = stats.by_source.get(source, 0) + 1

    candidates.sort(
        key=lambda candidate: (
            -candidate.evidence.score,
            candidate.from_entity_type,
            candidate.to_entity_type,
            candidate.candidate_id,
        )
    )
    if len(candidates) > limit:
        stats.truncated = len(candidates) - limit
        candidates = candidates[:limit]
    stats.generated = len(candidates)
    return CandidateGenerationResult(candidates=tuple(candidates), stats=stats)
