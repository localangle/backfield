"""Person-specific normalization, variants, blocking, and scoring.

Adapted from the ``backfield-reconciliation`` prototype and narrowed to the
production-safe pieces used by the ``duplicate-people`` cleanup check.

People matching is intentionally stricter than organizations: suffix-aware
guardrails, no broad last-name-only blocking, and conservative acceptance
thresholds reduce false positives on common names.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_PERSON_TITLES: frozenset[str] = frozenset(
    {
        "ambassador",
        "attorney",
        "brother",
        "chief",
        "commissioner",
        "director",
        "doctor",
        "dr",
        "father",
        "gov",
        "governor",
        "hon",
        "honorable",
        "judge",
        "madam",
        "mayor",
        "miss",
        "mr",
        "mrs",
        "ms",
        "president",
        "prof",
        "professor",
        "rep",
        "representative",
        "rev",
        "reverend",
        "secretary",
        "sen",
        "senator",
        "sir",
        "sister",
    }
)

_NAME_SUFFIXES: frozenset[str] = frozenset(
    {"ii", "iii", "iv", "jr", "junior", "senior", "sr", "v", "vi"}
)

_COMMON_FIRST_NAMES: frozenset[str] = frozenset(
    {
        "alex",
        "andrew",
        "anthony",
        "chris",
        "christopher",
        "daniel",
        "david",
        "james",
        "john",
        "joseph",
        "mark",
        "michael",
        "mike",
        "paul",
        "peter",
        "robert",
        "sarah",
        "steven",
        "thomas",
        "william",
    }
)

_COMMON_LAST_NAMES: frozenset[str] = frozenset(
    {
        "anderson",
        "brown",
        "clark",
        "davis",
        "doe",
        "garcia",
        "harris",
        "johnson",
        "jones",
        "lee",
        "martin",
        "miller",
        "moore",
        "robinson",
        "smith",
        "taylor",
        "thomas",
        "walker",
        "white",
        "williams",
        "wilson",
        "young",
    }
)

_GENERIC_GROUP_TOKENS: frozenset[str] = frozenset(
    {
        "attorneys",
        "deputies",
        "deputy",
        "detective",
        "detectives",
        "judges",
        "officer",
        "officers",
        "prosecutors",
        "troopers",
    }
)

_ORG_LOCATION_TOKENS: frozenset[str] = frozenset(
    {
        "administration",
        "authority",
        "board",
        "bureau",
        "committee",
        "company",
        "corporation",
        "council",
        "county",
        "court",
        "department",
        "district",
        "division",
        "government",
        "office",
        "police",
        "team",
        "university",
    }
)

DEFAULT_PERSON_ACCEPT_THRESHOLD: float = 0.88
DEFAULT_PERSON_MAX_BLOCK_SIZE: int = 250


def normalize_person_label(value: str) -> str:
    """Normalize punctuation, diacritics, and whitespace for person labels."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize_person(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(normalize_person_label(value)))


def _strip_titles(tokens: tuple[str, ...]) -> tuple[str, ...]:
    while tokens and tokens[0] in _PERSON_TITLES:
        tokens = tokens[1:]
    return tokens


def _split_suffix(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], str | None]:
    if not tokens:
        return (), None
    if tokens[-1] in _NAME_SUFFIXES:
        return tokens[:-1], tokens[-1]
    return tokens, None


def _collapse_initials(tokens: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    buffer: list[str] = []
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            buffer.append(token)
            continue
        if buffer:
            result.append("".join(buffer))
            buffer = []
        result.append(token)
    if buffer:
        result.append("".join(buffer))
    return tuple(result)


def _without_middle_initials(tokens: tuple[str, ...]) -> tuple[str, ...]:
    if len(tokens) <= 2:
        return tokens
    middle = tokens[1:-1]
    if not middle:
        return tokens
    kept = [token for token in middle if len(token) > 1 or not token.isalpha()]
    if len(kept) == len(middle):
        return tokens
    return (tokens[0], *kept, tokens[-1])


def core_person_name_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Return identity-bearing tokens with titles stripped and suffix removed."""
    return _split_suffix(_strip_titles(tokens))[0]


def build_person_variants(label: str) -> frozenset[str]:
    """Produce equivalent-form label variants used for exact-variant matching."""
    base = normalize_person_label(label)
    variants: set[str] = {base} if base else set()

    tokens = tokenize_person(base)
    stripped = _strip_titles(tokens)
    core, suffix = _split_suffix(stripped)

    title_stripped = " ".join(stripped)
    if title_stripped:
        variants.add(title_stripped)

    def _with_suffix(name_tokens: tuple[str, ...]) -> str:
        if suffix:
            return " ".join((*name_tokens, suffix))
        return " ".join(name_tokens)

    if core:
        variants.add(_with_suffix(core))

    collapsed = _collapse_initials(core)
    if collapsed and collapsed != core:
        variants.add(_with_suffix(collapsed))

    without_middle = _without_middle_initials(core)
    if without_middle and without_middle != core:
        variants.add(_with_suffix(without_middle))

    collapsed_without_middle = _collapse_initials(without_middle)
    if collapsed_without_middle:
        variants.add(_with_suffix(collapsed_without_middle))

    return frozenset(variant for variant in variants if variant)


def _should_add_first_last_key(core_tokens: tuple[str, ...]) -> bool:
    if len(core_tokens) < 2:
        return False
    first, last = core_tokens[0], core_tokens[-1]
    if first in _COMMON_FIRST_NAMES and last in _COMMON_LAST_NAMES:
        return False
    if len(last) <= 3 and last not in _NAME_SUFFIXES:
        return False
    return True


def build_person_blocking_keys(label: str) -> frozenset[str]:
    """Produce bounded blocking keys without broad last-name-only blocking."""
    variants = build_person_variants(label)
    tokens = tokenize_person(label)
    stripped = _strip_titles(tokens)
    core_tokens, suffix = _split_suffix(stripped)
    warnings = _profile_warnings(label, tokens, core_tokens)

    keys: set[str] = {f"variant:{variant}" for variant in variants}
    normalized = normalize_person_label(label)
    if normalized:
        keys.add(f"exact:{normalized}")

    if "generic_group_label" in warnings or "org_like" in warnings:
        return frozenset(keys)

    if _should_add_first_last_key(core_tokens):
        keys.add(f"first-last:{core_tokens[0]}:{core_tokens[-1]}")
        if suffix:
            keys.add(f"first-last-suffix:{core_tokens[0]}:{core_tokens[-1]}:{suffix}")

    return frozenset(keys)


@dataclass(frozen=True)
class PersonDuplicateProfile:
    """Per-canonical duplicate-matching profile."""

    id: str
    label: str
    person_type: str | None
    normalized_label: str
    tokens: tuple[str, ...]
    core_name_tokens: tuple[str, ...]
    suffix: str | None
    variants: frozenset[str]
    blocking_keys: frozenset[str]
    warnings: tuple[str, ...]


def _profile_warnings(
    label: str,
    tokens: tuple[str, ...],
    core_tokens: tuple[str, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if len(label.strip()) <= 3 or len(core_tokens) <= 1:
        warnings.append("short_or_ambiguous_label")
    if set(tokens) & _ORG_LOCATION_TOKENS:
        warnings.append("org_like")
    if any(token in _GENERIC_GROUP_TOKENS for token in tokens) or (
        any(token.isdigit() for token in tokens)
        and any(token in _GENERIC_GROUP_TOKENS for token in tokens)
    ):
        warnings.append("generic_group_label")
    return tuple(dict.fromkeys(warnings))


def build_person_profile(
    *,
    canonical_id: str,
    label: str,
    person_type: str | None,
) -> PersonDuplicateProfile:
    clean_label = (label or "").strip()
    tokens = tokenize_person(clean_label)
    stripped = _strip_titles(tokens)
    core_tokens, suffix = _split_suffix(stripped)
    return PersonDuplicateProfile(
        id=str(canonical_id),
        label=clean_label,
        person_type=(person_type.strip().lower() if person_type else None),
        normalized_label=normalize_person_label(clean_label),
        tokens=tokens,
        core_name_tokens=core_tokens,
        suffix=suffix,
        variants=build_person_variants(clean_label),
        blocking_keys=build_person_blocking_keys(clean_label),
        warnings=_profile_warnings(clean_label, tokens, core_tokens),
    )


@dataclass(frozen=True)
class PersonDuplicateEdge:
    """A scored candidate duplicate edge with human-readable reasons."""

    left_id: str
    right_id: str
    score: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    signal_scores: dict[str, float] = field(default_factory=dict)


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _shared_distinctive_token_count(
    left: PersonDuplicateProfile,
    right: PersonDuplicateProfile,
) -> int:
    left_tokens = set(left.core_name_tokens) - _COMMON_FIRST_NAMES - _COMMON_LAST_NAMES
    right_tokens = set(right.core_name_tokens) - _COMMON_FIRST_NAMES - _COMMON_LAST_NAMES
    return len(left_tokens & right_tokens)


def _numeric_tokens(profile: PersonDuplicateProfile) -> frozenset[str]:
    return frozenset(token for token in profile.tokens if token.isdigit())


def _suffix_mismatch(left: PersonDuplicateProfile, right: PersonDuplicateProfile) -> bool:
    left_suffix = left.suffix
    right_suffix = right.suffix
    if left_suffix == right_suffix:
        return False
    if left_suffix and right_suffix and left_suffix != right_suffix:
        return True
    if left_suffix or right_suffix:
        left_core = set(left.core_name_tokens)
        right_core = set(right.core_name_tokens)
        if left_core == right_core:
            return True
        if left_core <= right_core or right_core <= left_core:
            return True
    return False


def _weak_first_suffix_bridge(left: PersonDuplicateProfile, right: PersonDuplicateProfile) -> bool:
    if not left.suffix or left.suffix != right.suffix:
        return False
    left_core = left.core_name_tokens
    right_core = right.core_name_tokens
    if len(left_core) < 2 or len(right_core) < 2:
        return False
    return left_core[0] == right_core[0] and left_core[-1] != right_core[-1]


def _generic_group_numeric_mismatch(
    left: PersonDuplicateProfile,
    right: PersonDuplicateProfile,
) -> bool:
    left_group = "generic_group_label" in left.warnings
    right_group = "generic_group_label" in right.warnings
    if not left_group and not right_group:
        return False
    left_nums = _numeric_tokens(left)
    right_nums = _numeric_tokens(right)
    return bool(left_nums and right_nums and left_nums != right_nums)


def _org_like_without_exact_match(
    left: PersonDuplicateProfile,
    right: PersonDuplicateProfile,
) -> bool:
    org_like = "org_like" in left.warnings or "org_like" in right.warnings
    if not org_like:
        return False
    return left.normalized_label != right.normalized_label


_SUBSTANTIVE_REASON_PREFIXES: tuple[str, ...] = (
    "exact_normalized_name",
    "shared_variant:",
    "high_label_similarity",
    "high_token_overlap",
)

_STRONG_IDENTITY_PREFIXES: tuple[str, ...] = (
    "exact_normalized_name",
    "shared_variant:",
)

_NON_SUBSTANTIVE_REASONS: frozenset[str] = frozenset(
    {
        "generic_group_label",
        "org_like_label",
        "person_type_mismatch",
        "suffix_mismatch",
        "weak_first_suffix_bridge",
        "weak_text_similarity",
    }
)


def _has_substantive_reason(reasons: tuple[str, ...]) -> bool:
    for reason in reasons:
        if reason in _NON_SUBSTANTIVE_REASONS:
            continue
        if reason.startswith("same_person_type:"):
            continue
        if any(reason.startswith(prefix) for prefix in _SUBSTANTIVE_REASON_PREFIXES):
            return True
    return False


def _has_strong_identity_signal(reasons: tuple[str, ...]) -> bool:
    return any(
        reason == "exact_normalized_name" or reason.startswith("shared_variant:")
        for reason in reasons
    )


def _strong_support_signal_count(reasons: tuple[str, ...]) -> int:
    count = 0
    for reason in reasons:
        if reason in {"high_token_overlap", "high_label_similarity"}:
            count += 1
    return count


def score_person_pair(
    left: PersonDuplicateProfile,
    right: PersonDuplicateProfile,
) -> PersonDuplicateEdge:
    """Score one candidate pair and return the edge with explanatory reasons."""
    signal_scores: dict[str, float] = {}
    reasons: list[str] = []
    warnings = tuple(dict.fromkeys((*left.warnings, *right.warnings)))

    shared_distinctive = _shared_distinctive_token_count(left, right)
    suffix_mismatch = _suffix_mismatch(left, right)
    weak_suffix_bridge = _weak_first_suffix_bridge(left, right)
    generic_group_mismatch = _generic_group_numeric_mismatch(left, right)
    org_like_guard = _org_like_without_exact_match(left, right)
    numeric_mismatch = bool(
        _numeric_tokens(left)
        and _numeric_tokens(right)
        and _numeric_tokens(left) != _numeric_tokens(right)
    )
    person_type_mismatch = bool(
        left.person_type and right.person_type and left.person_type != right.person_type
    )

    if left.normalized_label and left.normalized_label == right.normalized_label:
        signal_scores["exact_normalized_name"] = 1.0
        reasons.append("exact_normalized_name")

    shared_variants = left.variants & right.variants
    generic_group_exact_only = (
        ("generic_group_label" in left.warnings or "generic_group_label" in right.warnings)
        and left.normalized_label != right.normalized_label
    )
    if (
        shared_variants
        and not generic_group_mismatch
        and not org_like_guard
        and not generic_group_exact_only
    ):
        signal_scores["shared_normalized_variant"] = 0.95
        reasons.append(f"shared_variant:{sorted(shared_variants)[0]}")

    has_identity_signal = bool(signal_scores)

    if left.person_type and left.person_type == right.person_type:
        signal_scores["same_person_type"] = 0.81
        reasons.append(f"same_person_type:{left.person_type}")

    token_overlap = _jaccard(set(left.core_name_tokens), set(right.core_name_tokens))
    if shared_distinctive < 2:
        token_overlap = min(token_overlap, 0.83)
    labels_differ = left.normalized_label != right.normalized_label
    if (numeric_mismatch or generic_group_mismatch) and labels_differ:
        token_overlap = min(token_overlap, 0.83)
    if org_like_guard and not has_identity_signal:
        token_overlap = min(token_overlap, 0.83)
    signal_scores["token_overlap"] = token_overlap
    if token_overlap >= 0.75:
        reasons.append("high_token_overlap")

    if left.variants and right.variants:
        raw_label_similarity = max(
            _ratio(left_variant, right_variant)
            for left_variant in left.variants
            for right_variant in right.variants
        )
    else:
        raw_label_similarity = _ratio(left.normalized_label, right.normalized_label)
    label_similarity = raw_label_similarity
    if shared_distinctive < 2:
        label_similarity = min(label_similarity, 0.83)
    if (numeric_mismatch or generic_group_mismatch) and labels_differ:
        label_similarity = min(label_similarity, 0.83)
    if person_type_mismatch and not has_identity_signal:
        label_similarity = min(label_similarity, 0.83)
    if org_like_guard and not has_identity_signal:
        label_similarity = min(label_similarity, 0.83)
    signal_scores["label_similarity"] = label_similarity
    if label_similarity >= 0.9:
        reasons.append("high_label_similarity")

    score = max(signal_scores.values(), default=0.0)
    if suffix_mismatch:
        score = min(score, 0.83)
        reasons.append("suffix_mismatch")
    if weak_suffix_bridge and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("weak_first_suffix_bridge")
    if generic_group_mismatch and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("generic_group_label")
    if org_like_guard and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("org_like_label")
    if person_type_mismatch and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("person_type_mismatch")
    if not reasons:
        reasons.append("weak_text_similarity")

    return PersonDuplicateEdge(
        left_id=left.id,
        right_id=right.id,
        score=score,
        reasons=tuple(reasons),
        warnings=warnings,
        signal_scores=signal_scores,
    )


def generate_person_pair_edges(
    profiles: list[PersonDuplicateProfile],
    *,
    threshold: float = DEFAULT_PERSON_ACCEPT_THRESHOLD,
    max_block_size: int = DEFAULT_PERSON_MAX_BLOCK_SIZE,
) -> list[PersonDuplicateEdge]:
    """Return accepted candidate edges after bounded blocking and scoring."""
    if len(profiles) < 2:
        return []

    profiles_by_id: dict[str, PersonDuplicateProfile] = {
        profile.id: profile for profile in profiles
    }
    by_key: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        for key in profile.blocking_keys:
            by_key[key].append(profile.id)

    candidate_pairs: set[tuple[str, str]] = set()
    for key, ids in by_key.items():
        unique_ids = sorted(set(ids))
        if len(unique_ids) < 2:
            continue
        if len(unique_ids) > max_block_size and not key.startswith("exact:"):
            continue
        for left_id, right_id in combinations(unique_ids, 2):
            candidate_pairs.add((left_id, right_id))

    accepted: list[PersonDuplicateEdge] = []
    for left_id, right_id in sorted(candidate_pairs):
        left = profiles_by_id[left_id]
        right = profiles_by_id[right_id]
        edge = score_person_pair(left, right)
        if edge.score < threshold:
            continue
        if not _has_substantive_reason(edge.reasons):
            continue
        needs_two_support_signals = (
            not _has_strong_identity_signal(edge.reasons)
            and _strong_support_signal_count(edge.reasons) < 2
        )
        if needs_two_support_signals:
            continue
        accepted.append(edge)
    return accepted
