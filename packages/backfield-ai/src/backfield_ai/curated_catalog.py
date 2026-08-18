"""Flagship curated AI presets derived from LiteLLM's model cost map."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from backfield_db.curated_ai_models import (
    AI_CAPABILITY_EMBEDDING,
    AI_CAPABILITY_JSON,
    AI_CAPABILITY_TEXT,
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
    CuratedAiModelTemplate,
)

# UI section order; providers not listed sort after these.
CURATED_PROVIDER_ORDER: tuple[str, ...] = (
    "openai",
    "anthropic",
    "gemini",
    "openrouter",
    "mistral",
)

OPENROUTER_FAMILIES: tuple[str, ...] = ("qwen", "deepseek")
OPENROUTER_FAMILY_LIMIT = 3

_DROP_SUBSTRINGS: tuple[str, ...] = (
    "audio",
    "realtime",
    "search",
    "transcribe",
    "tts",
    "instruct",
    "image",
    "computer-use",
    "computer_use",
    "preview",
    "experimental",
    "codex",
    "chat-latest",
)
_DATED_RE = re.compile(
    r"(?:-\d{4}-\d{2}-\d{2}|-\d{8}|-\d{2}-\d{2})(?:$|[-:])"
)
_BEDROCK_SUFFIX_RE = re.compile(r":\d+$")
_ZERO_PADDED_DATE_SUFFIX_RE = re.compile(r"-0\d{3}$")
_GPT_RE = re.compile(
    r"^gpt-(\d+)(?:\.(\d+))?(-mini|-nano|-pro|-sol|-terra|-luna)?$"
)
_ANTHROPIC_FAMILY_FIRST_RE = re.compile(
    r"^claude-(opus|sonnet|haiku)-(\d+)(?:-(\d+))?$"
)
_ANTHROPIC_VERSION_FIRST_RE = re.compile(
    r"^claude-(\d+)(?:-(\d+))?-(opus|sonnet|haiku)$"
)
_GEMINI_RE = re.compile(r"^gemini-(\d+)\.(\d+)-(pro|flash|flash-lite)$")
_EMBEDDING_RE = re.compile(r"^text-embedding-3-[a-z0-9-]+$")
_MISTRAL_RE = re.compile(r"^mistral-(large|medium|small)-latest$")
_OPENROUTER_QWEN_VERSION_RE = re.compile(r"qwen(\d+(?:\.\d+)?)")
_OPENROUTER_DEEPSEEK_V_RE = re.compile(r"v(\d+)(?:\.(\d+))?", re.IGNORECASE)
_OPENROUTER_DEEPSEEK_R_RE = re.compile(r"(?:^|[^a-z])r(\d+)(?:$|[^a-z0-9])", re.IGNORECASE)
_GPT_MIN_VERSION = (4, 1)
_ANTHROPIC_FAMILY_RANK = {"opus": 0, "sonnet": 1, "haiku": 2}
_GEMINI_TIER_RANK = {"pro": 0, "flash": 1, "flash-lite": 2}
_GPT_VARIANT_RANK = {
    "": 0,
    "-sol": 1,
    "-terra": 2,
    "-luna": 3,
    "-pro": 4,
    "-mini": 5,
    "-nano": 6,
}
_MISTRAL_SIZE_RANK = {"large": 0, "medium": 1, "small": 2}


def list_curated_templates(
    model_cost: Mapping[str, Any] | None = None,
) -> dict[str, CuratedAiModelTemplate]:
    """Return flagship presets keyed by curated id, in presentation order.

    When ``model_cost`` is omitted, use LiteLLM's in-process cost map (fetched from
    GitHub at import unless ``LITELLM_LOCAL_MODEL_COST_MAP`` is true).
    """
    cost_map = model_cost if model_cost is not None else _litellm_model_cost()
    collected: list[CuratedAiModelTemplate] = []
    seen_ids: set[str] = set()
    openrouter_by_family: dict[str, list[CuratedAiModelTemplate]] = {
        family: [] for family in OPENROUTER_FAMILIES
    }

    for key, entry in cost_map.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        template = _template_from_cost_entry(key, entry)
        if template is None or template.template_id in seen_ids:
            continue
        seen_ids.add(template.template_id)
        if template.provider == "openrouter":
            family = template.provider_model_id.split("/", 1)[0].lower()
            if family in openrouter_by_family:
                openrouter_by_family[family].append(template)
            continue
        collected.append(template)

    for family in OPENROUTER_FAMILIES:
        ranked = sorted(
            openrouter_by_family[family],
            key=_openrouter_newest_first_key,
        )
        collected.extend(ranked[:OPENROUTER_FAMILY_LIMIT])

    collected.sort(key=_presentation_sort_key)
    return {template.template_id: template for template in collected}


def _litellm_model_cost() -> Mapping[str, Any]:
    import litellm

    model_cost = getattr(litellm, "model_cost", None)
    if not isinstance(model_cost, dict):
        return {}
    return model_cost


def _template_from_cost_entry(
    key: str,
    entry: Mapping[str, Any],
) -> CuratedAiModelTemplate | None:
    raw_id = key.strip()
    if not raw_id or raw_id == "sample_spec":
        return None
    if _is_excluded_model_id(raw_id):
        return None
    mode = str(entry.get("mode") or "").strip().lower()

    openai = _openai_template(raw_id, mode)
    if openai is not None:
        return openai
    anthropic = _anthropic_template(raw_id, mode)
    if anthropic is not None:
        return anthropic
    gemini = _gemini_template(raw_id, mode)
    if gemini is not None:
        return gemini
    openrouter = _openrouter_template(raw_id, mode)
    if openrouter is not None:
        return openrouter
    return _mistral_template(raw_id, mode)


def _is_excluded_model_id(model_id: str) -> bool:
    lowered = model_id.lower()
    if _BEDROCK_SUFFIX_RE.search(lowered):
        return True
    if _DATED_RE.search(lowered):
        return True
    if _ZERO_PADDED_DATE_SUFFIX_RE.search(lowered):
        return True
    if lowered.endswith("-exp") or "-exp-" in lowered:
        return True
    return any(token in lowered for token in _DROP_SUBSTRINGS)


def _is_chat_mode(mode: str) -> bool:
    return mode in {"", "chat", "responses"}


def _openai_template(raw_id: str, mode: str) -> CuratedAiModelTemplate | None:
    if "/" in raw_id:
        return None
    if _EMBEDDING_RE.fullmatch(raw_id):
        if mode not in {"", "embedding"}:
            return None
        return CuratedAiModelTemplate(
            template_id=_curated_id("openai", raw_id),
            provider="openai",
            provider_model_id=raw_id,
            label=raw_id,
            capabilities=(AI_CAPABILITY_EMBEDDING,),
            model_kind=AI_MODEL_KIND_EMBEDDING,
        )
    match = _GPT_RE.fullmatch(raw_id)
    if match is None or not _is_chat_mode(mode):
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if (major, minor) < _GPT_MIN_VERSION:
        return None
    return _generative("openai", raw_id, _gpt_label(raw_id))


def _anthropic_template(raw_id: str, mode: str) -> CuratedAiModelTemplate | None:
    model_id = _strip_provider_prefix(raw_id, "anthropic")
    if model_id is None or not _is_chat_mode(mode):
        return None
    if (
        _ANTHROPIC_FAMILY_FIRST_RE.fullmatch(model_id) is None
        and _ANTHROPIC_VERSION_FIRST_RE.fullmatch(model_id) is None
    ):
        return None
    return _generative("anthropic", model_id, _anthropic_label(model_id))


def _gemini_template(raw_id: str, mode: str) -> CuratedAiModelTemplate | None:
    model_id = _strip_provider_prefix(raw_id, "gemini")
    if model_id is None or not _is_chat_mode(mode):
        return None
    if _GEMINI_RE.fullmatch(model_id) is None:
        return None
    return _generative("gemini", model_id, _gemini_label(model_id))


def _openrouter_template(raw_id: str, mode: str) -> CuratedAiModelTemplate | None:
    if not raw_id.startswith("openrouter/"):
        return None
    if not _is_chat_mode(mode):
        return None
    provider_model_id = raw_id.removeprefix("openrouter/").strip()
    family = provider_model_id.split("/", 1)[0].lower()
    if family not in OPENROUTER_FAMILIES or "/" not in provider_model_id:
        return None
    return _generative(
        "openrouter",
        provider_model_id,
        _openrouter_label(provider_model_id),
    )


def _mistral_template(raw_id: str, mode: str) -> CuratedAiModelTemplate | None:
    model_id = _strip_provider_prefix(raw_id, "mistral")
    if model_id is None or not _is_chat_mode(mode):
        return None
    if _MISTRAL_RE.fullmatch(model_id) is None:
        return None
    size = model_id.split("-")[1]
    return _generative("mistral", model_id, f"Mistral {size.title()}")


def _strip_provider_prefix(raw_id: str, provider: str) -> str | None:
    prefix = f"{provider}/"
    if raw_id.startswith(prefix):
        rest = raw_id[len(prefix) :].strip()
        return rest or None
    if "/" in raw_id:
        return None
    return raw_id.strip() or None


def _generative(
    provider: str,
    provider_model_id: str,
    label: str,
) -> CuratedAiModelTemplate:
    return CuratedAiModelTemplate(
        template_id=_curated_id(provider, provider_model_id),
        provider=provider,
        provider_model_id=provider_model_id,
        label=label,
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
        model_kind=AI_MODEL_KIND_GENERATIVE,
    )


def _curated_id(provider: str, provider_model_id: str) -> str:
    slug = provider_model_id.replace("/", "-")
    return f"{provider}:{slug}"


def _gpt_label(model_id: str) -> str:
    _prefix, version, *variants = model_id.split("-")
    parts = [f"GPT-{version}", *[part.title() for part in variants]]
    return " ".join(parts)


def _anthropic_label(model_id: str) -> str:
    family_first = _ANTHROPIC_FAMILY_FIRST_RE.fullmatch(model_id)
    if family_first is not None:
        family = family_first.group(1).title()
        version = _dotted_version(family_first.group(2), family_first.group(3))
        return f"Claude {family} {version}"
    version_first = _ANTHROPIC_VERSION_FIRST_RE.fullmatch(model_id)
    if version_first is None:
        return _title_hyphen_id(model_id)
    version = _dotted_version(version_first.group(1), version_first.group(2))
    family = version_first.group(3).title()
    return f"Claude {version} {family}"


def _gemini_label(model_id: str) -> str:
    match = _GEMINI_RE.fullmatch(model_id)
    if match is None:
        return _title_hyphen_id(model_id)
    version = f"{match.group(1)}.{match.group(2)}"
    tier = match.group(3).replace("-", " ").title()
    return f"Gemini {version} {tier}"


def _openrouter_label(provider_model_id: str) -> str:
    tail = provider_model_id.rsplit("/", 1)[-1]
    bits: list[str] = []
    for part in tail.split("-"):
        lowered = part.lower()
        if lowered == "deepseek":
            bits.append("DeepSeek")
        elif lowered.startswith("qwen"):
            bits.append(part[0].upper() + part[1:])
        elif re.fullmatch(r"r\d+", lowered):
            bits.append(part.upper())
        else:
            bits.append(part.title())
    return " ".join(bits)


def _title_hyphen_id(model_id: str) -> str:
    return " ".join(part.title() for part in model_id.replace("/", "-").split("-"))


def _dotted_version(major: str, minor: str | None) -> str:
    if minor:
        return f"{major}.{minor}"
    return major


def _presentation_sort_key(template: CuratedAiModelTemplate) -> tuple[Any, ...]:
    provider_rank = _provider_rank(template.provider)
    kind_rank = 1 if template.model_kind == AI_MODEL_KIND_EMBEDDING else 0
    if template.provider == "openai" and template.model_kind == AI_MODEL_KIND_GENERATIVE:
        match = _GPT_RE.fullmatch(template.provider_model_id)
        major = int(match.group(1)) if match else 0
        minor = int(match.group(2) or 0) if match else 0
        variant = match.group(3) or "" if match else ""
        return (
            kind_rank,
            provider_rank,
            -major,
            -minor,
            _GPT_VARIANT_RANK.get(variant, 99),
            template.provider_model_id,
        )
    if template.provider == "anthropic":
        family, major, minor = _anthropic_version_parts(template.provider_model_id)
        return (
            kind_rank,
            provider_rank,
            -major,
            -minor,
            _ANTHROPIC_FAMILY_RANK.get(family, 99),
            template.provider_model_id,
        )
    if template.provider == "gemini":
        match = _GEMINI_RE.fullmatch(template.provider_model_id)
        major = int(match.group(1)) if match else 0
        minor = int(match.group(2) or 0) if match else 0
        tier = match.group(3) if match else ""
        return (
            kind_rank,
            provider_rank,
            -major,
            -minor,
            _GEMINI_TIER_RANK.get(tier, 99),
            template.provider_model_id,
        )
    if template.provider == "openrouter":
        family = template.provider_model_id.split("/", 1)[0]
        family_rank = (
            OPENROUTER_FAMILIES.index(family) if family in OPENROUTER_FAMILIES else 99
        )
        return (kind_rank, provider_rank, family_rank, *_openrouter_newest_first_key(template))
    if template.provider == "mistral":
        match = _MISTRAL_RE.fullmatch(template.provider_model_id)
        size = match.group(1) if match else ""
        return (
            kind_rank,
            provider_rank,
            _MISTRAL_SIZE_RANK.get(size, 99),
            template.provider_model_id,
        )
    return (kind_rank, provider_rank, template.provider_model_id)


def _openrouter_newest_first_key(template: CuratedAiModelTemplate) -> tuple[Any, ...]:
    major, minor = _openrouter_version_tuple(template.provider_model_id)
    extras = _openrouter_extra_numbers(template.provider_model_id)
    negated_extras = tuple(-value for value in extras)
    return (-major, -minor, negated_extras, template.provider_model_id)


def _openrouter_extra_numbers(provider_model_id: str) -> tuple[int, ...]:
    _family, _, rest = provider_model_id.partition("/")
    return tuple(int(part) for part in re.findall(r"\d+", rest))


def _openrouter_version_tuple(provider_model_id: str) -> tuple[int, int]:
    family, _, rest = provider_model_id.partition("/")
    if family == "qwen":
        match = _OPENROUTER_QWEN_VERSION_RE.search(rest)
        if match is None:
            return (0, 0)
        return _split_numeric_version(match.group(1))
    if family == "deepseek":
        v_match = _OPENROUTER_DEEPSEEK_V_RE.search(rest)
        if v_match is not None:
            return (int(v_match.group(1)), int(v_match.group(2) or 0))
        r_match = _OPENROUTER_DEEPSEEK_R_RE.search(rest)
        if r_match is not None:
            return (int(r_match.group(1)), 0)
        return (0, 0)
    return (0, 0)


def _split_numeric_version(raw: str) -> tuple[int, int]:
    major_s, _, minor_s = raw.partition(".")
    return (int(major_s), int(minor_s or 0))


def _anthropic_version_parts(model_id: str) -> tuple[str, int, int]:
    family_first = _ANTHROPIC_FAMILY_FIRST_RE.fullmatch(model_id)
    if family_first is not None:
        return (
            family_first.group(1),
            int(family_first.group(2)),
            int(family_first.group(3) or 0),
        )
    version_first = _ANTHROPIC_VERSION_FIRST_RE.fullmatch(model_id)
    if version_first is None:
        return ("", 0, 0)
    return (
        version_first.group(3),
        int(version_first.group(1)),
        int(version_first.group(2) or 0),
    )


def _provider_rank(provider: str) -> int:
    try:
        return CURATED_PROVIDER_ORDER.index(provider)
    except ValueError:
        return len(CURATED_PROVIDER_ORDER)
