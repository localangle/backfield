"""Person canonical recall for ingest policy and LLM adjudication payloads."""

from __future__ import annotations

from backfield_db import StylebookPersonAlias, StylebookPersonCanonical, SubstratePerson
from sqlmodel import Session, col, select

from backfield_stylebook.entities.person.types import normalize_person_text

# Recall-biased floor: include weak name overlap for LLM adjudication (cap applied after sort).
PERSON_RECALL_MIN_SCORE = 20
PERSON_RECALL_DEFAULT_LIMIT = 24


def _person_name_norm(person: SubstratePerson) -> str:
    return normalize_person_text(person.normalized_name or person.name)


def _score_canonical_for_person(
    *,
    norm: str,
    title_norm: str,
    aff_norm: str,
    canon: StylebookPersonCanonical,
) -> int:
    score = 0
    label_norm = normalize_person_text(canon.label)
    if label_norm == norm:
        score += 100
    elif norm and (norm in label_norm or label_norm in norm):
        score += 40
    if title_norm and normalize_person_text(canon.title) == title_norm:
        score += 20
    if aff_norm and normalize_person_text(canon.affiliation) == aff_norm:
        score += 20
    return score


def _canonical_ids_from_exact_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> list[str]:
    norm = str(normalized_name).strip()
    if not norm:
        return []
    stmt = (
        select(StylebookPersonCanonical.id)
        .join(
            StylebookPersonAlias,
            StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
        )
        .where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonAlias.normalized_alias == norm,
            StylebookPersonAlias.suppressed.is_(False),
        )
    )
    out: list[str] = []
    seen: set[str] = set()
    for row in session.exec(stmt).all():
        if row is None:
            continue
        cid = str(row)
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def retrieve_person_canonical_candidates(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    limit: int = PERSON_RECALL_DEFAULT_LIMIT,
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` for policy defer and LLM adjudication (max ``limit``)."""
    norm = _person_name_norm(person)
    if not norm:
        return []

    title_norm = normalize_person_text(person.title)
    aff_norm = normalize_person_text(person.affiliation)
    scored: dict[str, tuple[int, str]] = {}

    for cid in _canonical_ids_from_exact_alias(
        session, stylebook_id=stylebook_id, normalized_name=norm
    ):
        canon = session.get(StylebookPersonCanonical, cid)
        if canon is None or canon.id is None:
            continue
        score = _score_canonical_for_person(
            norm=norm,
            title_norm=title_norm,
            aff_norm=aff_norm,
            canon=canon,
        )
        scored[str(canon.id)] = (max(score, 100), str(canon.label))

    label_stmt = (
        select(StylebookPersonCanonical)
        .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
        .order_by(col(StylebookPersonCanonical.label).asc())
        .limit(max(limit * 4, 48))
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        cid = str(canon.id)
        score = _score_canonical_for_person(
            norm=norm,
            title_norm=title_norm,
            aff_norm=aff_norm,
            canon=canon,
        )
        if score < PERSON_RECALL_MIN_SCORE:
            continue
        prev = scored.get(cid)
        if prev is None or score > prev[0]:
            scored[cid] = (score, str(canon.label))

    ranked = sorted(scored.items(), key=lambda item: (-item[1][0], item[1][1].lower()))
    out: list[tuple[str, str]] = []
    for cid, (_score, label) in ranked:
        out.append((cid, label))
        if len(out) >= limit:
            break
    return out
