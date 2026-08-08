"""Cross-chunk person stitching for named and abbreviated references."""

from __future__ import annotations

from typing import Any

from backfield_entities.entities.person.name_match import score_person_name_overlap
from backfield_entities.entities.person.name_mismatch import (
    person_family_names_conflict,
    person_given_names_conflict,
)
from backfield_entities.entities.person.types import normalize_person_text, person_match_key

from agate_nodes.extraction.grounding import ChunkCandidate, union_mention_texts


def _name_tokens(name: str) -> list[str]:
    return [tok for tok in normalize_person_text(name).split() if tok]


def _is_surname_only(name: str) -> bool:
    tokens = _name_tokens(name)
    return len(tokens) == 1 and tokens[0].isalpha() and len(tokens[0]) > 1


def _is_fuller_than(left: str, right: str) -> bool:
    return len(_name_tokens(left)) > len(_name_tokens(right))


def _mention_texts(person: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for mention in person.get("mentions") or []:
        if isinstance(mention, dict):
            text = mention.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def _merge_person_dicts(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    if _is_fuller_than(str(other.get("name") or ""), str(merged.get("name") or "")):
        merged["name"] = other["name"]
    for key in ("title", "affiliation", "type", "role_in_story", "nature"):
        if not merged.get(key) and other.get(key):
            merged[key] = other[key]
    if other.get("public_figure"):
        merged["public_figure"] = True
    mentions = []
    for text in union_mention_texts(_mention_texts(merged), _mention_texts(other)):
        mentions.append({"text": text, "quote": False})
    merged["mentions"] = mentions
    return merged


def _compatible_cluster(cluster: dict[str, Any], candidate: dict[str, Any]) -> bool:
    left = str(cluster.get("name") or "")
    right = str(candidate.get("name") or "")
    if not left or not right:
        return False
    if person_given_names_conflict(left, right) or person_family_names_conflict(left, right):
        return False
    if person_match_key(left) == person_match_key(right):
        return True
    if score_person_name_overlap(left, right) >= 85:
        return True
    # Surname-only abbreviation against a fuller name with the same family token.
    if _is_surname_only(right) and not _is_surname_only(left):
        family = _name_tokens(left)[-1]
        return family == _name_tokens(right)[0]
    if _is_surname_only(left) and not _is_surname_only(right):
        family = _name_tokens(right)[-1]
        return family == _name_tokens(left)[0]
    return False


def stitch_people_candidates(
    candidates: list[ChunkCandidate[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int]:
    """Merge owned person candidates; return people and unresolved abbreviation count."""
    owned = [c for c in candidates if c.owned and isinstance(c.payload, dict)]
    clusters: list[dict[str, Any]] = []
    unresolved = 0

    for candidate in sorted(owned, key=lambda c: (c.evidence.start if c.evidence else 0)):
        person = dict(candidate.payload)
        name = str(person.get("name") or "").strip()
        if not name:
            continue

        matches = [
            idx
            for idx, cluster in enumerate(clusters)
            if _compatible_cluster(cluster, person)
        ]
        if len(matches) == 1:
            clusters[matches[0]] = _merge_person_dicts(clusters[matches[0]], person)
            continue
        if len(matches) > 1:
            if _is_surname_only(name):
                unresolved += 1
                continue
            clusters.append(person)
            continue

        # Surname-only with zero or many fuller matches stays unresolved.
        if _is_surname_only(name):
            fuller = [
                idx
                for idx, cluster in enumerate(clusters)
                if not _is_surname_only(str(cluster.get("name") or ""))
                and _name_tokens(str(cluster.get("name") or ""))[-1:] == _name_tokens(name)
            ]
            if len(fuller) == 1:
                clusters[fuller[0]] = _merge_person_dicts(clusters[fuller[0]], person)
            else:
                unresolved += 1
            continue

        clusters.append(person)

    return clusters, unresolved
