"""Person canonical recall for ingest policy and LLM adjudication payloads."""

from __future__ import annotations

from backfield_db import StylebookPersonAlias, StylebookPersonCanonical, SubstratePerson
from sqlalchemy import or_
from sqlmodel import Session, col, select

from backfield_entities.entities.person.name_match import score_person_name_overlap
from backfield_entities.entities.person.types import (
    normalize_person_text,
    person_alias_lookup_keys,
    person_match_key,
    person_names_match,
)

# Recall-biased floor: include weak name overlap for LLM adjudication (cap applied after sort).
PERSON_RECALL_MIN_SCORE = 20
PERSON_RECALL_DEFAULT_LIMIT = 24


def canonical_ids_from_person_name_keys(
    session: Session,
    *,
    stylebook_id: int,
    name_or_norm: str,
    trusted_alias_only: bool = False,
) -> list[str]:
    """Canonical ids whose alias ``normalized_alias`` matches accent-insensitively.

    When ``trusted_alias_only`` is True, exclude ``substrate_ingest`` provenance so
    machine-written aliases cannot exact-match without editorial confirmation.
    """
    keys = person_alias_lookup_keys(name_or_norm)
    match_key = person_match_key(name_or_norm)
    if not keys and not match_key:
        return []
    lookup_keys = set(keys)
    if match_key:
        lookup_keys.add(match_key)
    filters = [
        StylebookPersonCanonical.stylebook_id == stylebook_id,
        StylebookPersonAlias.normalized_alias.in_(lookup_keys),
        StylebookPersonAlias.suppressed.is_(False),
    ]
    if trusted_alias_only:
        filters.append(StylebookPersonAlias.provenance != "substrate_ingest")
    stmt = (
        select(StylebookPersonCanonical.id, StylebookPersonAlias.normalized_alias)
        .join(
            StylebookPersonAlias,
            StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
        )
        .where(*filters)
    )
    out: list[str] = []
    seen: set[str] = set()
    for row in session.exec(stmt).all():
        cid, norm_alias = row[0], row[1]
        if cid is None:
            continue
        if match_key and person_match_key(str(norm_alias or "")) != match_key:
            continue
        cid_str = str(cid)
        if cid_str not in seen:
            seen.add(cid_str)
            out.append(cid_str)
    if out or not match_key:
        return out

    tokens = match_key.split()
    if not tokens:
        return []
    search_tok = tokens[0] if len(tokens[0]) >= 2 else tokens[-1]
    if len(search_tok) < 2:
        return []
    esc = search_tok.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pat = f"%{esc}%"
    scan_filters = [
        StylebookPersonCanonical.stylebook_id == stylebook_id,
        StylebookPersonAlias.suppressed.is_(False),
        col(StylebookPersonAlias.normalized_alias).like(pat, escape="\\"),
    ]
    if trusted_alias_only:
        scan_filters.append(StylebookPersonAlias.provenance != "substrate_ingest")
    scan_stmt = (
        select(StylebookPersonCanonical.id, StylebookPersonAlias.normalized_alias)
        .join(
            StylebookPersonAlias,
            StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
        )
        .where(*scan_filters)
        .limit(120)
    )
    for cid, norm_alias in session.exec(scan_stmt).all():
        if cid is None:
            continue
        if person_match_key(str(norm_alias or "")) != match_key:
            continue
        cid_str = str(cid)
        if cid_str not in seen:
            seen.add(cid_str)
            out.append(cid_str)
    return out


def _person_display_name(person: SubstratePerson) -> str:
    return str(person.name or person.normalized_name or "").strip()


def _person_name_norm(person: SubstratePerson) -> str:
    return normalize_person_text(person.normalized_name or person.name)


def alias_texts_for_canonical(
    session: Session,
    *,
    canon_id: str,
) -> list[str]:
    """Non-suppressed alias display strings for a canonical person."""
    return _alias_texts_for_canonical(session, canon_id=canon_id)


def _alias_texts_for_canonical(
    session: Session,
    *,
    canon_id: str,
) -> list[str]:
    rows = session.exec(
        select(StylebookPersonAlias.alias_text).where(
            StylebookPersonAlias.person_canonical_id == canon_id,
            StylebookPersonAlias.suppressed.is_(False),
        )
    ).all()
    return [str(r) for r in rows if r is not None and str(r).strip()]


def _score_canonical_for_person(
    session: Session,
    *,
    query_display: str,
    norm: str,
    title_norm: str,
    aff_norm: str,
    canon: StylebookPersonCanonical,
) -> int:
    cid = str(canon.id) if canon.id is not None else ""
    aliases = _alias_texts_for_canonical(session, canon_id=cid) if cid else []
    score = score_person_name_overlap(
        query_display,
        str(canon.label),
        extra_candidate_names=aliases,
    )
    if score == 0:
        if person_names_match(query_display, str(canon.label)):
            score = 100
        elif norm and person_match_key(str(canon.label)) and (
            norm in normalize_person_text(canon.label)
            or normalize_person_text(canon.label) in norm
        ):
            score = 40
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
    return canonical_ids_from_person_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=normalized_name,
    )


def _canonical_ids_from_token_alias_search(
    session: Session,
    *,
    stylebook_id: int,
    query_display: str,
) -> list[str]:
    """Canonical ids whose alias scores as a name overlap with ``query_display``."""
    from backfield_entities.entities.person.name_match import person_name_tokens

    _given, family, tokens = person_name_tokens(query_display)
    if not family and not tokens:
        return []
    search_toks = [family] if family else []
    for t in tokens:
        if t not in search_toks and len(t) >= 2:
            search_toks.append(t)
    if not search_toks:
        return []
    filters = []
    for tok in search_toks[:4]:
        esc = tok.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pat = f"%{esc}%"
        filters.append(col(StylebookPersonAlias.normalized_alias).like(pat, escape="\\"))
    if not filters:
        return []

    stmt = (
        select(StylebookPersonCanonical.id, StylebookPersonAlias.alias_text)
        .join(
            StylebookPersonAlias,
            StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
        )
        .where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonAlias.suppressed.is_(False),
            or_(*filters),
        )
        .limit(80)
    )
    out: list[str] = []
    seen: set[str] = set()
    for cid, alias_text in session.exec(stmt).all():
        if cid is None:
            continue
        cid_str = str(cid)
        if cid_str in seen:
            continue
        if score_person_name_overlap(query_display, str(alias_text)) >= PERSON_RECALL_MIN_SCORE:
            seen.add(cid_str)
            out.append(cid_str)
    return out


def retrieve_person_canonical_candidates(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    limit: int = PERSON_RECALL_DEFAULT_LIMIT,
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` for policy defer, LLM adjudication, and link UI."""
    query_display = _person_display_name(person)
    norm = _person_name_norm(person)
    if not norm:
        return []

    title_norm = normalize_person_text(person.title)
    aff_norm = normalize_person_text(person.affiliation)
    scored: dict[str, tuple[int, str]] = {}

    exact_alias_ids = set(
        _canonical_ids_from_exact_alias(
            session, stylebook_id=stylebook_id, normalized_name=norm
        )
    )
    candidate_ids: set[str] = set(exact_alias_ids)
    for cid in _canonical_ids_from_token_alias_search(
        session, stylebook_id=stylebook_id, query_display=query_display
    ):
        candidate_ids.add(cid)

    for cid in candidate_ids:
        canon = session.get(StylebookPersonCanonical, cid)
        if canon is None or canon.id is None:
            continue
        score = _score_canonical_for_person(
            session,
            query_display=query_display,
            norm=norm,
            title_norm=title_norm,
            aff_norm=aff_norm,
            canon=canon,
        )
        if score > 0:
            if cid in exact_alias_ids:
                score = max(score, 100)
            scored[str(canon.id)] = (score, str(canon.label))

    label_stmt = (
        select(StylebookPersonCanonical)
        .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
        .order_by(col(StylebookPersonCanonical.label).asc())
        .limit(max(limit * 8, 96))
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        cid = str(canon.id)
        score = _score_canonical_for_person(
            session,
            query_display=query_display,
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
