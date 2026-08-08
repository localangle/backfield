"""Cross-chunk organization stitching for names and acronyms."""

from __future__ import annotations

from typing import Any

from backfield_entities.entities.organization.types import (
    normalize_organization_text,
    organization_looks_like_acronym,
    organization_match_key,
    organization_names_match_via_acronym,
)

from agate_nodes.extraction.grounding import ChunkCandidate, union_mention_texts


def _mention_texts(org: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for mention in org.get("mentions") or []:
        if isinstance(mention, dict):
            text = mention.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def _prefer_expanded_name(left: str, right: str) -> str:
    left_n = normalize_organization_text(left)
    right_n = normalize_organization_text(right)
    if organization_looks_like_acronym(left_n) and not organization_looks_like_acronym(right_n):
        return right
    if organization_looks_like_acronym(right_n) and not organization_looks_like_acronym(left_n):
        return left
    return left if len(left_n) >= len(right_n) else right


def _merge_org_dicts(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged["name"] = _prefer_expanded_name(
        str(merged.get("name") or ""),
        str(other.get("name") or ""),
    )
    for key in ("type", "role_in_story", "nature", "organization_boundary"):
        if not merged.get(key) and other.get(key):
            merged[key] = other[key]
    mentions = []
    for text in union_mention_texts(_mention_texts(merged), _mention_texts(other)):
        mentions.append({"text": text, "quote": False})
    merged["mentions"] = mentions
    return merged


def _compatible(cluster: dict[str, Any], candidate: dict[str, Any]) -> bool:
    left = str(cluster.get("name") or "")
    right = str(candidate.get("name") or "")
    if not left or not right:
        return False
    if organization_match_key(left) == organization_match_key(right):
        return True
    return organization_names_match_via_acronym(left, right)


def stitch_organization_candidates(
    candidates: list[ChunkCandidate[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int]:
    owned = [c for c in candidates if c.owned and isinstance(c.payload, dict)]
    clusters: list[dict[str, Any]] = []
    unresolved = 0

    for candidate in sorted(owned, key=lambda c: (c.evidence.start if c.evidence else 0)):
        org = dict(candidate.payload)
        name = str(org.get("name") or "").strip()
        if not name:
            continue
        matches = [idx for idx, cluster in enumerate(clusters) if _compatible(cluster, org)]
        if len(matches) == 1:
            clusters[matches[0]] = _merge_org_dicts(clusters[matches[0]], org)
            continue
        if len(matches) > 1 and organization_looks_like_acronym(name):
            unresolved += 1
            continue
        if organization_looks_like_acronym(name) and not matches:
            unresolved += 1
            continue
        clusters.append(org)

    return clusters, unresolved
