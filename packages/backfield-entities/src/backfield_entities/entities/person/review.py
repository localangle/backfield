"""Person extract review routing: LLM labels plus deterministic overrides."""

from __future__ import annotations

import re
from typing import Any, Literal

ReviewHandling = Literal["none", "flag_review", "auto_defer"]

REVIEW_HANDLING_NONE: ReviewHandling = "none"
REVIEW_HANDLING_FLAG: ReviewHandling = "flag_review"
REVIEW_HANDLING_AUTO_DEFER: ReviewHandling = "auto_defer"

REASON_CHILD = "child"
REASON_ANIMAL = "animal"
REASON_STAGE_NAME_OR_ALIAS = "stage_name_or_alias"
REASON_FIRST_NAME_ONLY = "first_name_only"

AUTO_WAIVE_REASON_CODES: frozenset[str] = frozenset({REASON_CHILD, REASON_ANIMAL})
FLAG_REVIEW_REASON_CODES: frozenset[str] = frozenset(
    {REASON_STAGE_NAME_OR_ALIAS, REASON_FIRST_NAME_ONLY}
)

_DEFAULT_MESSAGES: dict[str, str] = {
    REASON_CHILD: "Identified as a child",
    REASON_ANIMAL: "Identified as an animal",
    REASON_STAGE_NAME_OR_ALIAS: "Stage name or alias — confirm full identity before linking",
    REASON_FIRST_NAME_ONLY: "First name only — confirm full identity before linking",
}

_INFERRED_SURNAME_REVIEW_MESSAGE = (
    "Surname inferred from a family reference — confirm full identity before linking"
)

_VALID_HANDLING: frozenset[str] = frozenset(
    {REVIEW_HANDLING_NONE, REVIEW_HANDLING_FLAG, REVIEW_HANDLING_AUTO_DEFER}
)
_VALID_REASON_CODES: frozenset[str] = AUTO_WAIVE_REASON_CODES | FLAG_REVIEW_REASON_CODES

_FIRST_NAME_ONLY_RE = re.compile(r"^[A-Z][a-z]{1,}$")


def default_review_message(code: str) -> str:
    return _DEFAULT_MESSAGES.get(code, "Needs review before canonical linking")


def is_auto_waive_review_code(code: str | None) -> bool:
    return str(code or "").strip() in AUTO_WAIVE_REASON_CODES


def is_flag_review_code(code: str | None) -> bool:
    return str(code or "").strip() in FLAG_REVIEW_REASON_CODES


def review_reason_dict(*, code: str, message: str | None = None) -> dict[str, str]:
    clean_code = str(code).strip()
    msg = (message or "").strip() or default_review_message(clean_code)
    return {"code": clean_code, "message": msg}


def _normalize_handling(value: Any) -> ReviewHandling:
    if not isinstance(value, str):
        return REVIEW_HANDLING_NONE
    s = value.strip().lower()
    if s in _VALID_HANDLING:
        return s  # type: ignore[return-value]
    return REVIEW_HANDLING_NONE


def _normalize_reason_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    return s if s in _VALID_REASON_CODES else None


def _optional_message(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _handling_for_reason(code: str) -> ReviewHandling:
    if code in AUTO_WAIVE_REASON_CODES:
        return REVIEW_HANDLING_AUTO_DEFER
    if code in FLAG_REVIEW_REASON_CODES:
        return REVIEW_HANDLING_FLAG
    return REVIEW_HANDLING_NONE


def parse_review_fields_from_entry(
    entry: dict[str, Any],
) -> tuple[ReviewHandling, str | None, str | None]:
    """Read LLM review fields from a consolidated ``people`` entry."""
    handling = _normalize_handling(entry.get("review_handling"))
    code = _normalize_reason_code(entry.get("review_reason_code"))
    message = _optional_message(entry.get("review_message"))
    if code is not None and handling == REVIEW_HANDLING_NONE:
        handling = _handling_for_reason(code)
    if code is not None and not message:
        message = default_review_message(code)
    if handling != REVIEW_HANDLING_NONE and code is None:
        handling = REVIEW_HANDLING_NONE
    return handling, code, message


def looks_like_first_name_only_token(name: str) -> bool:
    """Heuristic: short single Title-case token (e.g. ``Maria``), not mononyms like ``Prince``."""
    token = name.strip()
    if not token or " " in token or "." in token:
        return False
    if len(token) > 5:
        return False
    return _FIRST_NAME_ONLY_RE.fullmatch(token) is not None


def surname_inferred_from_relative(entry: dict[str, Any]) -> bool:
    """True when PersonExtract inferred a shared surname from a family reference."""
    val = entry.get("surname_inferred_from_relative")
    if val is True:
        return True
    if isinstance(val, str) and val.strip().lower() in {"true", "yes", "1"}:
        return True
    return False


def inferred_surname_from_review_message(message: str | None) -> bool:
    """Legacy rows may carry inferred-surname context only in ``review_message``."""
    text = str(message or "").strip().lower()
    if not text:
        return False
    return "inferred surname" in text or "surname inferred" in text


def person_inferred_surname_from_details(details: dict[str, Any]) -> bool:
    if surname_inferred_from_relative(details):
        return True
    return inferred_surname_from_review_message(
        details.get("review_message") if isinstance(details.get("review_message"), str) else None
    )


def review_reason_indicates_inferred_surname(reason: dict[str, Any]) -> bool:
    if str(reason.get("code") or "") != REASON_FIRST_NAME_ONLY:
        return False
    return inferred_surname_from_review_message(
        reason.get("message") if isinstance(reason.get("message"), str) else None
    )


def apply_inferred_surname_review_flag(
    entry: dict[str, Any],
    *,
    handling: ReviewHandling,
    reason_code: str | None,
    message: str | None,
) -> tuple[ReviewHandling, str | None, str | None]:
    """Force open-queue review for inferred surnames (same code as first-name-only)."""
    if not surname_inferred_from_relative(entry):
        return handling, reason_code, message
    if reason_code in AUTO_WAIVE_REASON_CODES:
        return handling, reason_code, message
    return (
        REVIEW_HANDLING_FLAG,
        REASON_FIRST_NAME_ONLY,
        message or _INFERRED_SURNAME_REVIEW_MESSAGE,
    )


def apply_deterministic_review_overrides(
    name: str,
    *,
    handling: ReviewHandling,
    reason_code: str | None,
    message: str | None,
) -> tuple[ReviewHandling, str | None, str | None]:
    """Apply rule-based review when the model left ``review_handling`` as ``none``."""
    if handling != REVIEW_HANDLING_NONE:
        return handling, reason_code, message
    if looks_like_first_name_only_token(name):
        code = REASON_FIRST_NAME_ONLY
        return (
            REVIEW_HANDLING_FLAG,
            code,
            message or default_review_message(code),
        )
    return handling, reason_code, message


def finalize_review_fields_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return review keys to merge onto a person entry (sets ``needs_review`` when flagged)."""
    name_raw = entry.get("name")
    name = name_raw.strip() if isinstance(name_raw, str) else ""
    handling, code, message = parse_review_fields_from_entry(entry)
    handling, code, message = apply_inferred_surname_review_flag(
        entry,
        handling=handling,
        reason_code=code,
        message=message,
    )
    if name:
        handling, code, message = apply_deterministic_review_overrides(
            name,
            handling=handling,
            reason_code=code,
            message=message,
        )
    needs_review = handling == REVIEW_HANDLING_FLAG
    out: dict[str, Any] = {
        "review_handling": handling,
        "review_reason_code": code,
        "review_message": message,
        "needs_review": needs_review,
    }
    return out


def review_context_from_source_details(
    details: dict[str, Any] | None,
) -> tuple[ReviewHandling, str | None, str | None]:
    if not isinstance(details, dict):
        return REVIEW_HANDLING_NONE, None, None
    handling = _normalize_handling(details.get("review_handling"))
    code = _normalize_reason_code(details.get("review_reason_code"))
    message = _optional_message(details.get("review_message"))
    if code is not None and handling == REVIEW_HANDLING_NONE:
        handling = _handling_for_reason(code)
    return handling, code, message


def entry_people_bucket(entry: dict[str, Any]) -> str:
    """Map consolidated entry to worker people bucket (``ready`` vs ``needs_review``)."""
    if entry.get("needs_review") is True:
        return "needs_review"
    handling, code, _msg = parse_review_fields_from_entry(entry)
    if handling == REVIEW_HANDLING_FLAG:
        return "needs_review"
    status = entry.get("status")
    if isinstance(status, str) and status.strip().lower() == "needs_review":
        return "needs_review"
    _ = code
    return "ready"


def plan_includes_person_review_defer(
    plan_reasons: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> bool:
    for r in plan_reasons:
        if not isinstance(r, dict):
            continue
        code = str(r.get("code") or "")
        if code in _VALID_REASON_CODES:
            return True
    return False


def plan_includes_auto_waive_person_review(
    plan_reasons: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> bool:
    for r in plan_reasons:
        if isinstance(r, dict) and is_auto_waive_review_code(str(r.get("code") or "")):
            return True
    return False


def plan_includes_flag_person_review(
    plan_reasons: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> bool:
    for r in plan_reasons:
        if isinstance(r, dict) and is_flag_review_code(str(r.get("code") or "")):
            return True
    return False


def plan_includes_defer_only_person_review(
    plan_reasons: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> bool:
    for r in plan_reasons:
        if not isinstance(r, dict):
            continue
        code = str(r.get("code") or "")
        if code in AUTO_WAIVE_REASON_CODES:
            return True
        if code == REASON_FIRST_NAME_ONLY:
            if isinstance(r, dict) and review_reason_indicates_inferred_surname(r):
                continue
            return True
    return False


def person_source_details(person: Any) -> dict[str, Any]:
    raw = getattr(person, "source_details_json", None)
    return raw if isinstance(raw, dict) else {}


def person_review_reason_code_from_source(details: dict[str, Any]) -> str | None:
    _handling, code, _message = review_context_from_source_details(details)
    return code


def person_surname_inferred_from_source(person: Any) -> bool:
    return person_inferred_surname_from_details(person_source_details(person))


def person_review_recommends_defer_only(
    *,
    reason_code: str | None,
    source_details: dict[str, Any] | None = None,
) -> bool:
    """True when editors should defer (no link/create recommendation)."""
    details = source_details if isinstance(source_details, dict) else {}
    if person_inferred_surname_from_details(details):
        return False
    code = str(reason_code or "").strip()
    if code in AUTO_WAIVE_REASON_CODES:
        return True
    return code == REASON_FIRST_NAME_ONLY


def person_review_blocks_auto_materialize(
    *,
    reason_code: str | None,
    source_details: dict[str, Any] | None = None,
) -> bool:
    """True when ingest must not auto-create a canonical (review queue may still suggest create)."""
    details = source_details if isinstance(source_details, dict) else {}
    if person_inferred_surname_from_details(details):
        return True
    code = str(reason_code or "").strip()
    if code == REASON_STAGE_NAME_OR_ALIAS:
        return True
    return person_review_recommends_defer_only(reason_code=code, source_details=details)
