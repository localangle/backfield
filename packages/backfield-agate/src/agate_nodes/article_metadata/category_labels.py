"""Allowed category label enforcement for Article Metadata prompts and parsing."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[^a-z0-9_]+")

_SPORTS_CHILDREN = ("pro_sports", "college_sports", "prep_youth_sports")

_GENERIC_PARENT_HINTS: dict[str, tuple[str, ...]] = {
    "sports": _SPORTS_CHILDREN,
    "sport": _SPORTS_CHILDREN,
}

# Common LLM paraphrases mapped to canonical topic slugs when present in allowed set.
_STATIC_ALIASES: dict[str, str] = {
    "economic_business": "business_economy",
    "business_economic": "business_economy",
    "economy_business": "business_economy",
    "business": "business_economy",
    "economy": "business_economy",
    "local_politics": "local_government_politics",
    "government_politics": "local_government_politics",
    "politics": "local_government_politics",
    "state_politics": "state_government_politics",
    "national_politics": "global_national_politics",
    "crime": "public_safety_crime",
    "public_safety": "public_safety_crime",
    "health": "health_public_health",
    "environment": "climate_environment",
    "climate": "climate_environment",
    "transportation": "transportation_transit",
    "traffic": "roads_traffic",
    "housing": "housing_development",
    "homelessness": "housing_affordability_homelessness",
    "real_estate": "real_estate_market",
    "education": "k12_education",
    "schools": "k12_education",
    "college": "higher_education",
    "science": "science_technology",
    "technology": "science_technology",
    "immigration": "immigration_demographics",
    "religion": "religion_faith",
    "food": "food_restaurants",
    "arts": "arts_culture",
    "culture": "arts_culture",
    "travel_tourism": "travel",
    "weather": "weather_natural_hazards",
    "disaster": "disaster_recovery",
    "labor": "labor_workforce",
    "workforce": "labor_workforce",
    "agriculture": "agriculture_rural",
    "rural": "agriculture_rural",
    "military": "military_veterans",
    "veterans": "military_veterans",
    "nonprofits": "nonprofits_philanthropy",
    "philanthropy": "nonprofits_philanthropy",
    "media": "media_journalism",
    "journalism": "media_journalism",
    "utilities": "utilities_energy",
    "energy": "utilities_energy",
    "zoning": "land_use_zoning",
    "land_use": "land_use_zoning",
    "outdoors": "outdoor_recreation",
    "recreation": "outdoor_recreation",
    "obituary": "obituaries",
    "recipe": "recipes",
    "accountability": "accountability_government_oversight",
    "legal": "courts_legal_system",
    "courts": "courts_legal_system",
    "consumer": "consumer_affairs",
    "animals": "animals_pets",
    "pets": "animals_pets",
    "events": "events_festivals",
    "festivals": "events_festivals",
    "community": "community_life",
}

_INVALID_CATEGORY_EXAMPLES = (
    "sports",
    "economic_business",
    "business",
    "politics",
    "education",
    "health",
    "crime",
)


def normalize_category_token(value: str) -> str:
    token = (value or "").strip().lower().replace("-", "_")
    token = _TOKEN_RE.sub("_", token)
    return token.strip("_")


def _slug_tokens(slug: str) -> list[str]:
    return [token for token in normalize_category_token(slug).split("_") if token]


def _expand_token_variants(token: str) -> set[str]:
    variants = {token}
    if token.endswith("ic"):
        variants.add(token[:-2] + "y")
    if token.endswith("y") and len(token) > 3:
        variants.add(token[:-1] + "ic")
    if token in {"economy", "economic"}:
        variants.update({"economy", "economic"})
    if token in {"business", "commerce"}:
        variants.add("business")
    return variants


def fuzzy_match_allowed_category(normalized: str, allowed: set[str]) -> str | None:
    """Match reordered or near-miss slugs such as economic_business -> business_economy."""
    input_tokens = _slug_tokens(normalized)
    if not input_tokens:
        return None

    best_slug: str | None = None
    best_score = 0.0
    for slug in allowed:
        slug_tokens = _slug_tokens(slug)
        input_expanded: set[str] = set()
        for token in input_tokens:
            input_expanded |= _expand_token_variants(token)
        slug_expanded: set[str] = set()
        for token in slug_tokens:
            slug_expanded |= _expand_token_variants(token)
        overlap = len(input_expanded & slug_expanded)
        if overlap == 0:
            continue
        score = overlap / max(len(input_tokens), len(slug_tokens))
        if score > best_score:
            best_score = score
            best_slug = slug

    if best_score >= 0.5 and best_slug is not None:
        return best_slug
    return None


def format_allowed_categories_enforcement(categories: list[str]) -> str:
    """Build prompt text that requires exact allowed category slugs."""
    slugs = [label.strip() for label in categories if label.strip()]
    if not slugs:
        return ""

    lines = [
        "## Allowed category values (enum — copy exactly)",
        "",
        "The category value must be copied **verbatim** from this list.",
        "Use the exact slug string (lowercase, underscores).",
        "Do not paraphrase, reorder words, shorten, pluralize, or invent labels.",
        "",
    ]
    for slug in slugs:
        lines.append(f"- `{slug}`")

    lines.extend(
        [
            "",
            "## Category slug rules (critical)",
            "- Output **only** a slug from the allowed list above.",
            "- Do **not** combine words differently (wrong: `economic_business`; "
            "right: `business_economy`).",
            "- Do **not** use generic domain words alone.",
            f"- Invalid examples: {', '.join(f'`{slug}`' for slug in _INVALID_CATEGORY_EXAMPLES)}.",
            "",
            "Complete allowed slug list (comma-separated):",
            ", ".join(f"`{slug}`" for slug in slugs),
        ]
    )

    sports_in_list = [slug for slug in slugs if slug in _SPORTS_CHILDREN]
    if sports_in_list:
        joined = ", ".join(f"`{slug}`" for slug in sports_in_list)
        lines.extend(
            [
                "",
                "Sports stories must use a specific sports slug, never generic labels "
                "like `sports` or `sport`.",
                f"Choose the best match from: {joined}.",
                "- `pro_sports`: professional teams and leagues (MLB, NFL, NBA, NHL, MLS, etc.)",
                "- `college_sports`: NCAA, college, or university athletics",
                "- `prep_youth_sports`: high school, prep, youth, or amateur club sports",
            ]
        )

    lines.extend(
        [
            "",
            "If none of the listed slugs fit, use `other` when it appears in the list.",
            "Never invent a new category name.",
        ]
    )
    return "\n".join(lines)


def build_category_retry_suffix(error_message: str, allowed_categories: list[str]) -> str:
    """Prompt suffix for a single corrective LLM retry after invalid categories."""
    slugs = sorted({label.strip() for label in allowed_categories if label.strip()})
    slug_list = ", ".join(f"`{slug}`" for slug in slugs)
    return (
        "\n\n## Correction required\n"
        f"{error_message.strip()}\n"
        "Your previous JSON used a category value that is **not** in the allowed slug list.\n"
        "Respond again with ONLY valid JSON.\n"
        "Copy each category slug **exactly** from this list — no synonyms or rewordings:\n"
        f"{slug_list}\n"
    )


def _resolve_sports_child(*, allowed: set[str], rationale: str | None) -> str | None:
    available = [slug for slug in _SPORTS_CHILDREN if slug in allowed]
    if not available:
        return None

    rationale_text = (rationale or "").lower()
    if any(token in rationale_text for token in ("high school", "prep", "youth", "teen")):
        if "prep_youth_sports" in allowed:
            return "prep_youth_sports"
    if any(
        token in rationale_text
        for token in ("college", "university", "ncaa", "gophers", "bulldogs", "huskies")
    ):
        if "college_sports" in allowed:
            return "college_sports"
    if "pro_sports" in allowed:
        return "pro_sports"
    if len(available) == 1:
        return available[0]
    return None


def _apply_static_alias(normalized: str, allowed: set[str]) -> str | None:
    target = _STATIC_ALIASES.get(normalized)
    if target and target in allowed:
        return target
    return None


def resolve_allowed_category(
    raw_category: str,
    allowed_categories: set[str],
    *,
    rationale: str | None = None,
    fallback_to_other: bool = False,
) -> str:
    """Map an LLM category token to an allowed slug when possible."""
    cleaned = raw_category.strip()
    if not cleaned:
        raise ValueError("category must be a non-empty string")

    if cleaned in allowed_categories:
        return cleaned

    by_lower = {slug.lower(): slug for slug in allowed_categories}
    normalized = normalize_category_token(cleaned)
    if normalized in by_lower:
        return by_lower[normalized]

    static_match = _apply_static_alias(normalized, allowed_categories)
    if static_match is not None:
        logger.warning(
            "[ArticleMetadata] mapped alias category %r to %r",
            cleaned,
            static_match,
        )
        return static_match

    if normalized in _GENERIC_PARENT_HINTS:
        sports_match = _resolve_sports_child(allowed=allowed_categories, rationale=rationale)
        if sports_match is not None:
            logger.warning(
                "[ArticleMetadata] mapped generic category %r to %r",
                cleaned,
                sports_match,
            )
            return sports_match
        children = _GENERIC_PARENT_HINTS[normalized]
        matches = [slug for slug in children if slug in allowed_categories]
        if len(matches) == 1:
            logger.warning(
                "[ArticleMetadata] mapped generic category %r to %r",
                cleaned,
                matches[0],
            )
            return matches[0]

    fuzzy_match = fuzzy_match_allowed_category(normalized, allowed_categories)
    if fuzzy_match is not None:
        logger.warning(
            "[ArticleMetadata] fuzzy-mapped category %r to %r",
            cleaned,
            fuzzy_match,
        )
        return fuzzy_match

    if fallback_to_other and "other" in allowed_categories:
        logger.warning(
            "[ArticleMetadata] falling back invalid category %r to other",
            cleaned,
        )
        return "other"

    return cleaned


def is_invalid_category_error(exc: BaseException) -> bool:
    return isinstance(exc, ValueError) and "not allowed" in str(exc)
