"""Organization-specific normalization, variants, blocking, and scoring.

Adapted from the ``backfield-reconciliation`` prototype and narrowed to the
production-safe pieces used by the ``duplicate-organizations`` cleanup check.

Everything here is pure Python and deterministic so SQLite tests and Postgres
runtime share the same behavior.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")

_STOPWORDS: frozenset[str] = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to"}
)

_ORG_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {"co", "company", "corp", "corporation", "inc", "incorporated", "llc", "ltd", "plc"}
)

_PERSON_TITLES: frozenset[str] = frozenset(
    {
        "ambassador",
        "attorney",
        "chief",
        "commissioner",
        "director",
        "doctor",
        "dr",
        "governor",
        "mayor",
        "mr",
        "mrs",
        "ms",
        "president",
        "professor",
        "rep",
        "representative",
        "sen",
        "senator",
        "secretary",
    }
)

_GENERIC_ADMIN_TOKENS: frozenset[str] = frozenset(
    {
        "administration",
        "agency",
        "authority",
        "board",
        "bureau",
        "commission",
        "committee",
        "council",
        "department",
        "division",
        "government",
        "office",
    }
)

# Tokens that show up in many unrelated organization names. Used to
# discount broad token-overlap edges and to require distinctive support
# for subset evidence.
_LOW_INFORMATION_TOKENS: frozenset[str] = frozenset(
    {
        "academy",
        "administration",
        "association",
        "attorney",
        "basketball",
        "baseball",
        "boys",
        "center",
        "city",
        "clerk",
        "college",
        "community",
        "congressional",
        "correctional",
        "county",
        "department",
        "district",
        "fire",
        "fighting",
        "football",
        "girls",
        "high",
        "il",
        "illini",
        "men",
        "mens",
        "office",
        "police",
        "school",
        "sheriff",
        "state",
        "team",
        "university",
        "ward",
        "women",
        "womens",
    }
)

_SPORT_TOKENS: frozenset[str] = frozenset(
    {"baseball", "basketball", "football", "hockey", "lacrosse", "soccer"}
)
_TEAM_SEGMENT_TOKENS: frozenset[str] = frozenset(
    {"boys", "girls", "men", "mens", "women", "womens"}
)

DEFAULT_ORG_ACCEPT_THRESHOLD: float = 0.84
DEFAULT_ORG_MAX_BLOCK_SIZE: int = 250
_MIN_ACRONYM_LEN: int = 3


def normalize_organization_label(value: str) -> str:
    """Normalize punctuation and whitespace while preserving reviewable words."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = normalized.casefold()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"\b(u)\.?\s*(s)\.?\b", "us", normalized)
    normalized = re.sub(r"['\u2018\u2019\u02bc\u0060]s\b", "s", normalized)
    normalized = re.sub(r"[^a-z0-9()]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _strip_parenthetical(value: str) -> str:
    return re.sub(r"\s+", " ", _PARENTHETICAL_RE.sub(" ", value)).strip()


def tokenize_organization(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(normalize_organization_label(value)))


def significant_organization_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        token
        for token in tokens
        if token not in _STOPWORDS
        and token not in _ORG_LEGAL_SUFFIXES
        and (len(token) > 1 or token.isdigit())
    )


def organization_acronym(tokens: tuple[str, ...]) -> str:
    sig_tokens = significant_organization_tokens(tokens)
    if len(sig_tokens) < 2:
        return ""
    return "".join(token[0] for token in sig_tokens if token)


def _without_titles(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(token for token in tokens if token not in _PERSON_TITLES)


def _administration_variant(tokens: tuple[str, ...]) -> str:
    """Reduce presidential administration references to a stable variant.

    ``Trump Administration`` and ``Donald Trump Administration`` both collapse
    to ``trump administration`` so they share a variant blocking key.
    """
    if "administration" not in tokens:
        return ""

    filtered = [
        token
        for token in _without_titles(tokens)
        if token not in _STOPWORDS
        and token not in {"donald", "president", "office", "united", "states", "us"}
    ]
    if "administration" not in filtered:
        filtered.append("administration")
    return " ".join(filtered)


def _jurisdiction_prefix(tokens: tuple[str, ...]) -> tuple[str, ...]:
    while tokens and tokens[0] in {"office", "of", "the"}:
        tokens = tokens[1:]

    if "county" in tokens:
        county_index = tokens.index("county")
        if county_index > 0:
            return (*tokens[: county_index + 1],)
    return tuple(token for token in tokens if token not in _STOPWORDS and token != "office")


def _states_attorney_variants(tokens: tuple[str, ...]) -> set[str]:
    """State's attorney office variants across ``office of the …`` / ``… office`` forms."""
    variants: set[str] = set()
    for index in range(len(tokens) - 1):
        if tokens[index] in {"state", "states"} and tokens[index + 1] in {
            "attorney",
            "attorneys",
        }:
            prefix = _jurisdiction_prefix(tokens[:index])
            if prefix:
                variants.add(" ".join((*prefix, "states", "attorneys", "office")))
    return variants


def _office_variants(tokens: tuple[str, ...]) -> set[str]:
    variants: set[str] = set()

    if tokens[:2] == ("office", "of"):
        remainder = tuple(token for token in tokens[2:] if token not in _STOPWORDS)
        if remainder:
            variants.add(" ".join((*remainder, "office")))

    if "office" in tokens:
        office_index = tokens.index("office")
        before_office = tokens[:office_index]
        if len(before_office) >= 3 and before_office[-1] not in _GENERIC_ADMIN_TOKENS:
            variants.add(" ".join((*before_office, "office")))

    variants.update(_states_attorney_variants(tokens))
    return variants


def build_organization_variants(label: str) -> frozenset[str]:
    """Produce equivalent-form label variants used for exact-variant matching."""
    base = normalize_organization_label(label)
    variants: set[str] = {base} if base else set()

    no_parenthetical = normalize_organization_label(_strip_parenthetical(label))
    if no_parenthetical:
        variants.add(no_parenthetical)

    tokens = tokenize_organization(base)
    title_stripped = " ".join(_without_titles(tokens))
    if title_stripped:
        variants.add(title_stripped)

    admin_variant = _administration_variant(tokens)
    if admin_variant:
        variants.add(admin_variant)

    variants.update(_office_variants(tokens))

    sig_tokens = significant_organization_tokens(tokens)
    sig = " ".join(sig_tokens)
    if sig:
        variants.add(sig)

    # Order-independent significant-token variant so reorderings like
    # "Finance Department" and "Department of Finance" share a variant
    # blocking key. Bounded: exactly one entry per profile.
    if len(sig_tokens) >= 2:
        distinctive = tuple(token for token in sig_tokens if token not in _LOW_INFORMATION_TOKENS)
        if len(distinctive) >= 2:
            variants.add(" ".join(sorted(sig_tokens)))

    return frozenset(variant for variant in variants if variant)


def build_organization_blocking_keys(label: str) -> frozenset[str]:
    """Produce bounded blocking keys that constrain candidate-pair generation."""
    variants = build_organization_variants(label)
    tokens = tokenize_organization(label)
    sig_tokens = significant_organization_tokens(tokens)

    keys: set[str] = {f"variant:{variant}" for variant in variants}
    normalized = normalize_organization_label(label)
    if normalized:
        keys.add(f"exact:{normalized}")

    if len(sig_tokens) >= 2:
        keys.add(f"first-last:{sig_tokens[0]}:{sig_tokens[-1]}")
        keys.add(f"last:{sig_tokens[-1]}")
        for token in sig_tokens:
            if len(token) > 3:
                keys.add(f"last-token:{sig_tokens[-1]}:{token}")

    acro = organization_acronym(tokens)
    if len(acro) >= _MIN_ACRONYM_LEN:
        keys.add(f"acronym:{acro}")

    return frozenset(keys)


@dataclass(frozen=True)
class OrganizationDuplicateProfile:
    """Per-canonical duplicate-matching profile."""

    id: str
    label: str
    organization_type: str | None
    normalized_label: str
    tokens: tuple[str, ...]
    significant_tokens: tuple[str, ...]
    variants: frozenset[str]
    blocking_keys: frozenset[str]


def build_organization_profile(
    *,
    canonical_id: str,
    label: str,
    organization_type: str | None,
) -> OrganizationDuplicateProfile:
    clean_label = (label or "").strip()
    tokens = tokenize_organization(clean_label)
    return OrganizationDuplicateProfile(
        id=str(canonical_id),
        label=clean_label,
        organization_type=(organization_type.strip().lower() if organization_type else None),
        normalized_label=normalize_organization_label(clean_label),
        tokens=tokens,
        significant_tokens=significant_organization_tokens(tokens),
        variants=build_organization_variants(clean_label),
        blocking_keys=build_organization_blocking_keys(clean_label),
    )


@dataclass(frozen=True)
class OrganizationDuplicateEdge:
    """A scored candidate duplicate edge with human-readable reasons."""

    left_id: str
    right_id: str
    score: float
    reasons: tuple[str, ...]
    signal_scores: dict[str, float] = field(default_factory=dict)


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _shared_distinctive_token_count(
    left: OrganizationDuplicateProfile,
    right: OrganizationDuplicateProfile,
) -> int:
    left_tokens = set(left.significant_tokens) - _LOW_INFORMATION_TOKENS
    right_tokens = set(right.significant_tokens) - _LOW_INFORMATION_TOKENS
    return len(left_tokens & right_tokens)


def _numeric_tokens(profile: OrganizationDuplicateProfile) -> frozenset[str]:
    return frozenset(token for token in profile.tokens if token.isdigit())


def _county_tokens(profile: OrganizationDuplicateProfile) -> frozenset[str]:
    tokens = profile.tokens
    counties: set[str] = set()
    for index, token in enumerate(tokens):
        if token == "county" and index > 0:
            counties.add(tokens[index - 1])
    return frozenset(counties)


def _sports_team_mismatch(
    left: OrganizationDuplicateProfile,
    right: OrganizationDuplicateProfile,
) -> bool:
    if left.organization_type != "sports_team" or right.organization_type != "sports_team":
        return False
    left_sports = set(left.tokens) & _SPORT_TOKENS
    right_sports = set(right.tokens) & _SPORT_TOKENS
    if left_sports and right_sports and left_sports != right_sports:
        return True
    left_segments = set(left.tokens) & _TEAM_SEGMENT_TOKENS
    right_segments = set(right.tokens) & _TEAM_SEGMENT_TOKENS
    return bool(left_segments and right_segments and left_segments != right_segments)


def _subset_support_score(
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
) -> float:
    """Return a supporting subset score when one significant-token set contains the other."""
    left = set(left_tokens)
    right = set(right_tokens)
    if len(left) < 2 or len(right) < 2:
        return 0.0
    if left <= right:
        smaller = left
    elif right <= left:
        smaller = right
    else:
        return 0.0
    distinctive = smaller - _LOW_INFORMATION_TOKENS
    if len(distinctive) < 2:
        return 0.0
    # Supporting evidence only; too broad as the strongest signal because
    # union-find would chain transitive subsets into one giant cluster.
    return 0.82


_SUBSTANTIVE_REASON_PREFIXES: tuple[str, ...] = (
    "exact_normalized_name",
    "shared_variant:",
    "high_label_similarity",
    "high_token_overlap",
    "shared_acronym:",
    "token_subset",
)

_NON_SUBSTANTIVE_REASONS: frozenset[str] = frozenset(
    {
        "weak_text_similarity",
        "organization_type_mismatch",
        "county_mismatch",
        "sports_team_mismatch",
    }
)


def _has_substantive_reason(reasons: tuple[str, ...]) -> bool:
    for reason in reasons:
        if reason in _NON_SUBSTANTIVE_REASONS:
            continue
        if reason.startswith("same_organization_type:"):
            continue
        if any(reason.startswith(prefix) for prefix in _SUBSTANTIVE_REASON_PREFIXES):
            return True
    return False


def score_organization_pair(
    left: OrganizationDuplicateProfile,
    right: OrganizationDuplicateProfile,
) -> OrganizationDuplicateEdge:
    """Score one candidate pair and return the edge with explanatory reasons."""
    signal_scores: dict[str, float] = {}
    reasons: list[str] = []

    shared_distinctive = _shared_distinctive_token_count(left, right)
    numeric_mismatch = bool(
        _numeric_tokens(left)
        and _numeric_tokens(right)
        and _numeric_tokens(left) != _numeric_tokens(right)
    )
    county_mismatch = bool(
        _county_tokens(left)
        and _county_tokens(right)
        and _county_tokens(left) != _county_tokens(right)
    )
    org_type_mismatch = bool(
        left.organization_type
        and right.organization_type
        and left.organization_type != right.organization_type
    )
    sports_mismatch = _sports_team_mismatch(left, right)

    if left.normalized_label and left.normalized_label == right.normalized_label:
        signal_scores["exact_normalized_name"] = 1.0
        reasons.append("exact_normalized_name")

    shared_variants = left.variants & right.variants
    if shared_variants:
        signal_scores["shared_normalized_variant"] = 0.95
        reasons.append(f"shared_variant:{sorted(shared_variants)[0]}")

    has_identity_signal = bool(signal_scores)

    if left.organization_type and left.organization_type == right.organization_type:
        # Supporting evidence only; never crosses accept threshold on its own.
        signal_scores["same_organization_type"] = 0.81
        reasons.append(f"same_organization_type:{left.organization_type}")

    token_overlap = _jaccard(set(left.significant_tokens), set(right.significant_tokens))
    if shared_distinctive < 2:
        token_overlap = min(token_overlap, 0.83)
    if (numeric_mismatch or county_mismatch) and left.normalized_label != right.normalized_label:
        token_overlap = min(token_overlap, 0.83)
    if sports_mismatch and not has_identity_signal:
        token_overlap = min(token_overlap, 0.83)
    signal_scores["token_overlap"] = token_overlap
    if token_overlap >= 0.75:
        reasons.append("high_token_overlap")

    subset_score = _subset_support_score(left.significant_tokens, right.significant_tokens)
    if subset_score:
        signal_scores["token_subset"] = subset_score
        reasons.append("token_subset")

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
    if (numeric_mismatch or county_mismatch) and left.normalized_label != right.normalized_label:
        label_similarity = min(label_similarity, 0.83)
    if org_type_mismatch and not has_identity_signal:
        label_similarity = min(label_similarity, 0.83)
    if sports_mismatch and not has_identity_signal:
        label_similarity = min(label_similarity, 0.83)
    signal_scores["label_similarity"] = label_similarity
    if label_similarity >= 0.9:
        reasons.append("high_label_similarity")

    left_acronym = organization_acronym(left.tokens)
    right_acronym = organization_acronym(right.tokens)
    if left_acronym and left_acronym == right_acronym:
        signal_scores["shared_acronym"] = 0.82
        reasons.append(f"shared_acronym:{left_acronym}")

    score = max(signal_scores.values(), default=0.0)
    if org_type_mismatch and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("organization_type_mismatch")
    if county_mismatch and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("county_mismatch")
    if sports_mismatch and not has_identity_signal:
        score = min(score, 0.83)
        reasons.append("sports_team_mismatch")
    if not reasons:
        reasons.append("weak_text_similarity")

    return OrganizationDuplicateEdge(
        left_id=left.id,
        right_id=right.id,
        score=score,
        reasons=tuple(reasons),
        signal_scores=signal_scores,
    )


def generate_organization_pair_edges(
    profiles: list[OrganizationDuplicateProfile],
    *,
    threshold: float = DEFAULT_ORG_ACCEPT_THRESHOLD,
    max_block_size: int = DEFAULT_ORG_MAX_BLOCK_SIZE,
) -> list[OrganizationDuplicateEdge]:
    """Return accepted candidate edges after bounded blocking and scoring."""
    if len(profiles) < 2:
        return []

    profiles_by_id: dict[str, OrganizationDuplicateProfile] = {p.id: p for p in profiles}
    by_key: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        for key in profile.blocking_keys:
            by_key[key].append(profile.id)

    candidate_pairs: set[tuple[str, str]] = set()
    for key, ids in by_key.items():
        unique_ids = sorted(set(ids))
        if len(unique_ids) < 2:
            continue
        # Skip oversized fuzzy blocks; never fall back to all-pairs. Exact
        # normalized matches remain covered by other blocking keys or the
        # exact-key path.
        if len(unique_ids) > max_block_size and not key.startswith("exact:"):
            continue
        for left_id, right_id in combinations(unique_ids, 2):
            candidate_pairs.add((left_id, right_id))

    accepted: list[OrganizationDuplicateEdge] = []
    for left_id, right_id in sorted(candidate_pairs):
        left = profiles_by_id[left_id]
        right = profiles_by_id[right_id]
        edge = score_organization_pair(left, right)
        if edge.score < threshold:
            continue
        if not _has_substantive_reason(edge.reasons):
            continue
        accepted.append(edge)
    return accepted
