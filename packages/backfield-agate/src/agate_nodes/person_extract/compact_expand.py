"""Compact PersonExtract array rows → full dict entries for ``person_from_llm_entry``."""

from __future__ import annotations

from typing import Any

from backfield_entities.entities.person.types import (
    PERSON_NATURE_VALUES,
    PERSON_TYPE_VALUES,
)

PERSON_TYPE_CODES: dict[str, str] = {
    "athlete": "ath",
    "coach": "coa",
    "sports_official": "spo",
    "sports_executive": "spx",
    "elected_official": "eo",
    "government_official": "go",
    "political_staff": "ps",
    "lawyer_legal_advocate": "law",
    "judge_court_official": "jud",
    "law_enforcement_public_safety": "le",
    "crime_justice_subject": "cj",
    "business_owner_executive": "boe",
    "business_professional": "bpr",
    "labor_union_representative": "lab",
    "artist_entertainer": "art",
    "media_journalism": "med",
    "arts_culture_professional": "acp",
    "education_research_expert": "edu",
    "healthcare_worker": "hcw",
    "community_member": "com",
    "unknown": "un",
    "other": "oth",
}

PERSON_TYPE_FROM_CODE: dict[str, str] = {
    code: slug for slug, code in PERSON_TYPE_CODES.items()
}

PERSON_NATURE_CODES: dict[str, str] = {
    "subject": "su",
    "source": "so",
    "expert": "ex",
    "official": "of",
    "witness": "wi",
    "affected": "af",
    "victim": "vi",
    "suspect": "sp",
    "participant": "pa",
    "observer": "ob",
    "context": "cx",
    "other": "ot",
}

PERSON_NATURE_FROM_CODE: dict[str, str] = {
    code: slug for slug, code in PERSON_NATURE_CODES.items()
}

PERSON_COMPACT_LEGEND = """\
Use these short codes in array columns 4 and 6 (type, nature):

type (column 4):
  ath athlete  coa coach  spo sports_official  spx sports_executive
  eo elected_official  go government_official  ps political_staff
  law lawyer_legal_advocate  jud judge_court_official
  le law_enforcement_public_safety  cj crime_justice_subject
  boe business_owner_executive  bpr business_professional  lab labor_union_representative
  art artist_entertainer  med media_journalism  acp arts_culture_professional
  edu education_research_expert  hcw healthcare_worker  com community_member
  un unknown  oth other

nature (column 6):
  su subject  so source  ex expert  of official  wi witness  af affected
  vi victim  sp suspect  pa participant  ob observer  cx context  ot other

extras (optional trailing object; omit when empty):
  st — array of nature codes for nature_secondary_tags
  si — 1 when surname_inferred_from_relative is true
  review — {"handling","reason_code","message"} when review_handling != "none"
"""


def expand_person_type(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return "unknown"
    if token in PERSON_TYPE_VALUES:
        return token
    expanded = PERSON_TYPE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def expand_person_nature(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return "other"
    if token in PERSON_NATURE_VALUES:
        return token
    expanded = PERSON_NATURE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def _coerce_bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _parse_mentions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("'mentions' field must be a list")
    mentions: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                mentions.append({"text": text, "quote": False})
            continue
        if isinstance(item, list) and len(item) >= 1:
            text = str(item[0] or "").strip()
            if not text:
                continue
            quote = _coerce_bool_flag(item[1]) if len(item) > 1 else False
            mentions.append({"text": text, "quote": quote})
            continue
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or "").strip()
            if text:
                mentions.append({"text": text, "quote": bool(item.get("quote", False))})
            continue
        raise ValueError("Each mention must be [text, quote] or an object with 'text' and 'quote'")
    return mentions


def _expand_nature_code_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = expand_person_nature(item)
        if slug in PERSON_NATURE_VALUES and slug not in out:
            out.append(slug)
    return out


def _apply_person_extras(entry: dict[str, Any], extras: dict[str, Any]) -> None:
    secondary = _expand_nature_code_list(extras.get("st"))
    if secondary:
        entry["nature_secondary_tags"] = secondary

    if _coerce_bool_flag(extras.get("si")):
        entry["surname_inferred_from_relative"] = True

    review = extras.get("review")
    if isinstance(review, dict):
        handling = review.get("handling")
        if handling is not None:
            entry["review_handling"] = str(handling).strip()
        reason_code = review.get("reason_code")
        if reason_code is not None:
            entry["review_reason_code"] = str(reason_code).strip()
        message = review.get("message")
        if message is not None:
            entry["review_message"] = str(message).strip()


def is_skippable_compact_row_error(message: str) -> bool:
    """True when a compact row is an LLM placeholder with no extractable person."""
    return message in {
        "person entry array must not be empty",
        "Missing required field 'name'",
    }


def expand_compact_person_row(row: list[Any]) -> dict[str, Any]:
    """Expand one compact person array row into a dict for ``person_from_llm_entry``."""
    if not isinstance(row, list):
        raise ValueError("person entry must be an array")
    if not row:
        raise ValueError("person entry array must not be empty")

    name = str(row[0] or "").strip()
    if not name:
        raise ValueError("Missing required field 'name'")

    title = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
    affiliation = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
    public_figure = _coerce_bool_flag(row[3]) if len(row) > 3 else False
    type_code = row[4] if len(row) > 4 else "un"
    role_in_story = str(row[5]).strip() if len(row) > 5 and row[5] is not None else ""
    nature_code = row[6] if len(row) > 6 else "ot"
    mentions_raw = row[7] if len(row) > 7 else []

    entry: dict[str, Any] = {
        "name": name,
        "title": title,
        "affiliation": affiliation,
        "public_figure": public_figure,
        "type": expand_person_type(type_code),
        "role_in_story": role_in_story,
        "nature": expand_person_nature(nature_code),
        "mentions": _parse_mentions(mentions_raw),
    }

    if len(row) > 8 and isinstance(row[8], dict):
        _apply_person_extras(entry, row[8])

    return entry
