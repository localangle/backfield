"""Organization AI model catalog: curated templates, validation, and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from backfield_ai.constants import (
    AI_CAPABILITY_JSON,
    AI_CAPABILITY_TEXT,
    AI_CAPABILITY_VISION,
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
    DEFAULT_AI_CURRENCY,
)
from backfield_ai.litellm_model import litellm_model_id
from backfield_db import BackfieldAiModelConfig
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

try:  # optional import; used only for curated pricing defaults
    import litellm  # type: ignore
except Exception:  # pragma: no cover
    litellm = None

ALLOWED_CAPABILITIES: frozenset[str] = frozenset(
    {AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON, AI_CAPABILITY_VISION}
)
ALLOWED_MODEL_KINDS: frozenset[str] = frozenset({AI_MODEL_KIND_GENERATIVE, AI_MODEL_KIND_EMBEDDING})
ALLOWED_STATUS: frozenset[str] = frozenset({"active", "disabled"})


@dataclass(frozen=True)
class CuratedAiModelTemplate:
    """Preset provider/model pair shipped with the product."""

    template_id: str
    provider: str
    provider_model_id: str
    label: str
    capabilities: tuple[str, ...]


CURATED_TEMPLATES: dict[str, CuratedAiModelTemplate] = {
    # OpenAI (ordered for quick selection).
    "openai:gpt-5-mini": CuratedAiModelTemplate(
        template_id="openai:gpt-5-mini",
        provider="openai",
        provider_model_id="gpt-5-mini",
        label="GPT-5 Mini",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5-nano": CuratedAiModelTemplate(
        template_id="openai:gpt-5-nano",
        provider="openai",
        provider_model_id="gpt-5-nano",
        label="GPT-5 Nano",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5": CuratedAiModelTemplate(
        template_id="openai:gpt-5",
        provider="openai",
        provider_model_id="gpt-5",
        label="GPT-5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.4-mini": CuratedAiModelTemplate(
        template_id="openai:gpt-5.4-mini",
        provider="openai",
        provider_model_id="gpt-5.4-mini",
        label="GPT-5.4 Mini",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.4-nano": CuratedAiModelTemplate(
        template_id="openai:gpt-5.4-nano",
        provider="openai",
        provider_model_id="gpt-5.4-nano",
        label="GPT-5.4 Nano",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.4": CuratedAiModelTemplate(
        template_id="openai:gpt-5.4",
        provider="openai",
        provider_model_id="gpt-5.4",
        label="GPT-5.4",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.5": CuratedAiModelTemplate(
        template_id="openai:gpt-5.5",
        provider="openai",
        provider_model_id="gpt-5.5",
        label="GPT-5.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.5-pro": CuratedAiModelTemplate(
        template_id="openai:gpt-5.5-pro",
        provider="openai",
        provider_model_id="gpt-5.5-pro",
        label="GPT-5.5 Pro",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-4o-mini": CuratedAiModelTemplate(
        template_id="openai:gpt-4o-mini",
        provider="openai",
        provider_model_id="gpt-4o-mini",
        label="GPT-4o Mini",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # Anthropic (recent generations).
    "anthropic:claude-sonnet-4-5": CuratedAiModelTemplate(
        template_id="anthropic:claude-sonnet-4-5",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-5-20250929",
        label="Claude Sonnet 4.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-sonnet-4-6": CuratedAiModelTemplate(
        template_id="anthropic:claude-sonnet-4-6",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-haiku-4-5": CuratedAiModelTemplate(
        template_id="anthropic:claude-haiku-4-5",
        provider="anthropic",
        provider_model_id="claude-haiku-4-5-20251001",
        label="Claude Haiku 4.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-opus-4-5": CuratedAiModelTemplate(
        template_id="anthropic:claude-opus-4-5",
        provider="anthropic",
        provider_model_id="claude-opus-4-5-20251101",
        label="Claude Opus 4.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-opus-4-7": CuratedAiModelTemplate(
        template_id="anthropic:claude-opus-4-7",
        provider="anthropic",
        provider_model_id="claude-opus-4-7-20260416",
        label="Claude Opus 4.7",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
}


class CuratedAiModelOptionOut(BaseModel):
    curated_id: str
    provider: str
    provider_model_id: str
    label: str
    capabilities: list[str]
    input_token_price: Decimal | None = None
    output_token_price: Decimal | None = None
    currency: str = DEFAULT_AI_CURRENCY


class AiModelConfigOut(BaseModel):
    id: str
    organization_id: int
    name: str
    provider: str
    provider_model_id: str
    model_kind: str
    status: str
    capabilities: list[str]
    config_json: dict[str, Any] | None = None
    input_token_price: Decimal | None = None
    output_token_price: Decimal | None = None
    currency: str
    latest_test_status: str | None = None
    latest_tested_at: str | None = None
    latest_test_error: str | None = None


class AiModelConfigCreateBody(BaseModel):
    """Create from a curated preset or as a custom LiteLLM-compatible model."""

    name: str | None = Field(
        default=None,
        description=(
            "Display name in this organization. Defaults to curated label when curated_id is set."
        ),
    )
    curated_id: str | None = Field(
        default=None,
        description="When set, provider and provider_model_id come from this curated template.",
    )
    provider: str | None = None
    provider_model_id: str | None = None
    model_kind: str = AI_MODEL_KIND_GENERATIVE
    capabilities: list[str] | None = None
    config_json: dict[str, Any] | None = None
    input_token_price: Decimal | None = None
    output_token_price: Decimal | None = None
    currency: str = DEFAULT_AI_CURRENCY


class AiModelConfigPatchBody(BaseModel):
    name: str | None = None
    status: str | None = None
    capabilities: list[str] | None = None
    config_json: dict[str, Any] | None = None
    input_token_price: Decimal | None = None
    output_token_price: Decimal | None = None
    currency: str | None = None
    model_kind: str | None = None


def list_curated_options_out() -> list[CuratedAiModelOptionOut]:
    templates = list(CURATED_TEMPLATES.values())
    return [
        CuratedAiModelOptionOut(
            curated_id=t.template_id,
            provider=t.provider,
            provider_model_id=t.provider_model_id,
            label=t.label,
            capabilities=list(t.capabilities),
            input_token_price=_litellm_price_per_token(t.provider, t.provider_model_id, "input"),
            output_token_price=_litellm_price_per_token(t.provider, t.provider_model_id, "output"),
            currency=DEFAULT_AI_CURRENCY,
        )
        for t in templates
    ]


def _litellm_price_per_token(
    provider: str,
    provider_model_id: str,
    which: str,
) -> Decimal | None:
    """Best-effort lookup of per-token pricing from LiteLLM's model cost map.

    Backfield stores provider/model separately. LiteLLM cost keys vary by provider, so try variants.
    """
    if litellm is None:
        return None

    key_candidates = [
        litellm_model_id(provider, provider_model_id),
        provider_model_id,
        f"{provider.strip().lower()}/{provider_model_id.strip()}",
    ]
    model_cost = getattr(litellm, "model_cost", None)
    if not isinstance(model_cost, dict):
        return None
    for key in key_candidates:
        entry = model_cost.get(key)
        if not isinstance(entry, dict):
            continue
        raw = entry.get("input_cost_per_token" if which == "input" else "output_cost_per_token")
        if raw is None:
            continue
        try:
            return Decimal(str(raw))
        except Exception:
            return None
    return None


def _normalize_currency(raw: str) -> str:
    c = raw.strip().upper()
    if len(c) != 3 or not c.isalpha():
        raise HTTPException(status_code=400, detail="currency must be a 3-letter code")
    return c


def _validate_model_kind(kind: str) -> str:
    k = kind.strip()
    if k not in ALLOWED_MODEL_KINDS:
        raise HTTPException(status_code=400, detail="Unsupported model_kind")
    return k


def _validate_capabilities(caps: list[str]) -> list[str]:
    if not caps:
        raise HTTPException(status_code=400, detail="capabilities must not be empty")
    unknown = sorted(set(caps) - ALLOWED_CAPABILITIES)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported capabilities: {', '.join(unknown)}",
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for c in caps:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _validate_optional_prices(
    inp: Decimal | None,
    out: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    def check(label: str, v: Decimal) -> None:
        if v < 0:
            raise HTTPException(status_code=400, detail=f"{label} must be zero or positive")

    if inp is not None:
        check("input_token_price", inp)
    if out is not None:
        check("output_token_price", out)
    return inp, out


def row_to_out(row: BackfieldAiModelConfig) -> AiModelConfigOut:
    tested_at = row.latest_tested_at.isoformat() if row.latest_tested_at else None
    return AiModelConfigOut(
        id=str(row.id),
        organization_id=int(row.organization_id),
        name=str(row.name),
        provider=str(row.provider),
        provider_model_id=str(row.provider_model_id),
        model_kind=str(row.model_kind),
        status=str(row.status),
        capabilities=list(row.capabilities_json or []),
        config_json=row.config_json,
        input_token_price=row.input_token_price,
        output_token_price=row.output_token_price,
        currency=str(row.currency),
        latest_test_status=row.latest_test_status,
        latest_tested_at=tested_at,
        latest_test_error=row.latest_test_error,
    )


def list_org_model_configs(session: Session, organization_id: int) -> list[AiModelConfigOut]:
    rows = session.exec(
        select(BackfieldAiModelConfig)
        .where(BackfieldAiModelConfig.organization_id == organization_id)
        .order_by(col(BackfieldAiModelConfig.name))
    ).all()
    return [row_to_out(r) for r in rows]


def get_org_model_config(
    session: Session,
    *,
    organization_id: int,
    config_id: str,
) -> BackfieldAiModelConfig:
    row = session.get(BackfieldAiModelConfig, config_id)
    if row is None or int(row.organization_id) != organization_id:
        raise HTTPException(status_code=404, detail="Model configuration not found")
    return row


def create_org_model_config(
    session: Session,
    organization_id: int,
    body: AiModelConfigCreateBody,
) -> AiModelConfigOut:
    model_kind = _validate_model_kind(body.model_kind)
    if model_kind != AI_MODEL_KIND_GENERATIVE:
        raise HTTPException(
            status_code=400,
            detail="Only generative models can be created through this endpoint for now",
        )
    currency = _normalize_currency(body.currency)
    inp_p, out_p = _validate_optional_prices(body.input_token_price, body.output_token_price)

    if body.curated_id:
        tmpl = CURATED_TEMPLATES.get(body.curated_id.strip())
        if tmpl is None:
            raise HTTPException(status_code=400, detail="Unknown curated_id")
        name = (body.name or tmpl.label).strip()
        provider = tmpl.provider.strip().lower()
        provider_model_id = tmpl.provider_model_id.strip()
        caps_raw = body.capabilities if body.capabilities is not None else list(tmpl.capabilities)
        if body.provider is not None and body.provider.strip().lower() != provider:
            raise HTTPException(
                status_code=400,
                detail="provider must match the curated template or be omitted",
            )
        if (
            body.provider_model_id is not None
            and body.provider_model_id.strip() != provider_model_id
        ):
            raise HTTPException(
                status_code=400,
                detail="provider_model_id must match the curated template or be omitted",
            )
    else:
        if not body.provider or not body.provider.strip():
            raise HTTPException(status_code=400, detail="provider is required for custom models")
        if not body.provider_model_id or not body.provider_model_id.strip():
            raise HTTPException(
                status_code=400,
                detail="provider_model_id is required for custom models",
            )
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="name is required for custom models")
        if body.capabilities is None:
            raise HTTPException(
                status_code=400,
                detail="capabilities is required for custom models",
            )
        name = body.name.strip()
        provider = body.provider.strip().lower()
        provider_model_id = body.provider_model_id.strip()
        caps_raw = body.capabilities

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    capabilities = _validate_capabilities(caps_raw)

    row = BackfieldAiModelConfig(
        organization_id=organization_id,
        name=name,
        provider=provider,
        provider_model_id=provider_model_id,
        model_kind=model_kind,
        status="active",
        capabilities_json=capabilities,
        config_json=body.config_json,
        input_token_price=inp_p,
        output_token_price=out_p,
        currency=currency,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A model configuration with this name already exists in the organization",
        ) from None
    session.refresh(row)
    return row_to_out(row)


def patch_org_model_config(
    session: Session,
    *,
    organization_id: int,
    config_id: str,
    body: AiModelConfigPatchBody,
) -> AiModelConfigOut:
    row = get_org_model_config(session, organization_id=organization_id, config_id=config_id)
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        row.name = name

    if "status" in data:
        st = str(data["status"]).strip().lower()
        if st not in ALLOWED_STATUS:
            raise HTTPException(status_code=400, detail="Unsupported status")
        row.status = st

    if "capabilities" in data:
        caps = data["capabilities"]
        if caps is None:
            raise HTTPException(status_code=400, detail="capabilities must not be null")
        row.capabilities_json = _validate_capabilities(list(caps))

    if "config_json" in data:
        row.config_json = data["config_json"]

    if "currency" in data and data["currency"] is not None:
        row.currency = _normalize_currency(str(data["currency"]))

    if "model_kind" in data and data["model_kind"] is not None:
        mk = _validate_model_kind(str(data["model_kind"]))
        if mk != AI_MODEL_KIND_GENERATIVE:
            raise HTTPException(
                status_code=400,
                detail="Only generative models are supported for now",
            )
        row.model_kind = mk

    if "input_token_price" in data or "output_token_price" in data:
        new_in = row.input_token_price
        new_out = row.output_token_price
        if "input_token_price" in data:
            new_in = data["input_token_price"]
        if "output_token_price" in data:
            new_out = data["output_token_price"]
        new_in, new_out = _validate_optional_prices(new_in, new_out)
        row.input_token_price = new_in
        row.output_token_price = new_out

    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A model configuration with this name already exists in the organization",
        ) from None
    session.refresh(row)
    return row_to_out(row)


def run_org_model_connection_test(
    session: Session,
    organization_id: int,
    config_id: str,
) -> AiModelConfigOut:
    """Tiny LiteLLM ping; updates latest test columns only (no LLM call records)."""
    from backfield_ai.completion import completion_text_sync
    from backfield_ai.credentials import organization_llm_api_keys
    from backfield_ai.litellm_model import litellm_model_id

    row = get_org_model_config(session, organization_id=organization_id, config_id=config_id)
    keys = organization_llm_api_keys(session, organization_id)
    lm = litellm_model_id(str(row.provider), str(row.provider_model_id))
    prov = str(row.provider).strip().lower()
    if prov == "openai":
        api_key = keys.get("OPENAI_API_KEY")
    elif prov == "anthropic":
        api_key = keys.get("ANTHROPIC_API_KEY")
    else:
        api_key = keys.get("OPENAI_API_KEY") or keys.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No provider credentials configured for this organization",
        )

    now = datetime.now(UTC)
    try:
        messages = [
            {"role": "system", "content": "Reply with exactly OK."},
            {"role": "user", "content": "ping"},
        ]
        is_gpt5 = lm.startswith("gpt-5")
        temp = None if is_gpt5 else 0.0
        completion_text_sync(
            litellm_model=lm,
            messages=messages,
            api_key=api_key,
            max_tokens=8,
            temperature=temp,
            timeout=60.0,
            force_json_response=False,
        )
        row.latest_test_status = "succeeded"
        row.latest_test_error = None
    except Exception as exc:  # noqa: BLE001 — safe summary only on config row
        row.latest_test_status = "failed"
        row.latest_test_error = str(exc)[:2000]
    row.latest_tested_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row_to_out(row)
