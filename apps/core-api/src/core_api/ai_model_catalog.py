"""Organization AI model catalog: curated templates, validation, and persistence helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from backfield_ai.constants import (
    AI_CAPABILITY_EMBEDDING,
    AI_CAPABILITY_JSON,
    AI_CAPABILITY_TEXT,
    AI_CAPABILITY_VISION,
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
    DEFAULT_AI_CURRENCY,
    is_project_model_override_integration_key,
)
from backfield_ai.litellm_model import (
    effective_litellm_model_row,
    litellm_model_cost_lookup_keys,
)
from backfield_db import (
    BackfieldAiCallRecord,
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldOrganizationIntegrationSecret,
)
from backfield_db.crypto import decrypt_secret
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from core_api.org_integration_secrets import (
    assert_integration_secret_assignable_for_catalog_model,
)

try:  # optional import; used only for curated pricing defaults
    import litellm  # type: ignore
except Exception:  # pragma: no cover
    litellm = None

ALLOWED_CAPABILITIES: frozenset[str] = frozenset(
    {
        AI_CAPABILITY_TEXT,
        AI_CAPABILITY_JSON,
        AI_CAPABILITY_VISION,
        AI_CAPABILITY_EMBEDDING,
    }
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
    model_kind: str = AI_MODEL_KIND_GENERATIVE


# Insertion order controls default API list order and Preset dropdown order within each provider.
CURATED_TEMPLATES: dict[str, CuratedAiModelTemplate] = {
    # --- OpenAI ---
    "openai:gpt-5.5": CuratedAiModelTemplate(
        template_id="openai:gpt-5.5",
        provider="openai",
        provider_model_id="gpt-5.5",
        label="GPT-5.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-5.4": CuratedAiModelTemplate(
        template_id="openai:gpt-5.4",
        provider="openai",
        provider_model_id="gpt-5.4",
        label="GPT-5.4",
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
    "openai:gpt-5": CuratedAiModelTemplate(
        template_id="openai:gpt-5",
        provider="openai",
        provider_model_id="gpt-5",
        label="GPT-5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
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
    "openai:gpt-4.1": CuratedAiModelTemplate(
        template_id="openai:gpt-4.1",
        provider="openai",
        provider_model_id="gpt-4.1",
        label="GPT-4.1",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openai:gpt-4.1-mini": CuratedAiModelTemplate(
        template_id="openai:gpt-4.1-mini",
        provider="openai",
        provider_model_id="gpt-4.1-mini",
        label="GPT-4.1 Mini",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # --- Anthropic ---
    "anthropic:claude-opus-4-6": CuratedAiModelTemplate(
        template_id="anthropic:claude-opus-4-6",
        provider="anthropic",
        provider_model_id="claude-opus-4-6",
        label="Claude Opus 4.6",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-sonnet-4-6": CuratedAiModelTemplate(
        template_id="anthropic:claude-sonnet-4-6",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-opus-4-5": CuratedAiModelTemplate(
        template_id="anthropic:claude-opus-4-5",
        provider="anthropic",
        provider_model_id="claude-opus-4-5",
        label="Claude Opus 4.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-sonnet-4-5": CuratedAiModelTemplate(
        template_id="anthropic:claude-sonnet-4-5",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-5",
        label="Claude Sonnet 4.5",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-opus-4-1": CuratedAiModelTemplate(
        template_id="anthropic:claude-opus-4-1",
        provider="anthropic",
        provider_model_id="claude-opus-4-1",
        label="Claude Opus 4.1",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-sonnet-4": CuratedAiModelTemplate(
        template_id="anthropic:claude-sonnet-4",
        provider="anthropic",
        provider_model_id="claude-sonnet-4",
        label="Claude Sonnet 4",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "anthropic:claude-3-7-sonnet-20250219": CuratedAiModelTemplate(
        template_id="anthropic:claude-3-7-sonnet-20250219",
        provider="anthropic",
        provider_model_id="claude-3-7-sonnet-20250219",
        label="Claude 3.7 Sonnet",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # --- Google Gemini (LiteLLM routes gemini/gemini-* — provider slug ``gemini``) ---
    "gemini:gemini-2.5-pro": CuratedAiModelTemplate(
        template_id="gemini:gemini-2.5-pro",
        provider="gemini",
        provider_model_id="gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "gemini:gemini-2.5-flash": CuratedAiModelTemplate(
        template_id="gemini:gemini-2.5-flash",
        provider="gemini",
        provider_model_id="gemini-2.5-flash",
        label="Gemini 2.5 Flash",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "gemini:gemini-2.5-flash-lite": CuratedAiModelTemplate(
        template_id="gemini:gemini-2.5-flash-lite",
        provider="gemini",
        provider_model_id="gemini-2.5-flash-lite",
        label="Gemini 2.5 Flash Lite",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "gemini:gemini-2.0-flash": CuratedAiModelTemplate(
        template_id="gemini:gemini-2.0-flash",
        provider="gemini",
        provider_model_id="gemini-2.0-flash",
        label="Gemini 2.0 Flash",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # --- OpenRouter ---
    "openrouter:qwen-qwen3.6-plus": CuratedAiModelTemplate(
        template_id="openrouter:qwen-qwen3.6-plus",
        provider="openrouter",
        provider_model_id="qwen/qwen3.6-plus",
        label="Qwen3.6 Plus",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openrouter:qwen-qwen3.6-35b-a3b": CuratedAiModelTemplate(
        template_id="openrouter:qwen-qwen3.6-35b-a3b",
        provider="openrouter",
        provider_model_id="qwen/qwen3.6-35b-a3b",
        label="Qwen3.6 35B A3B",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openrouter:qwen-qwen3-235b-a22b-2507": CuratedAiModelTemplate(
        template_id="openrouter:qwen-qwen3-235b-a22b-2507",
        provider="openrouter",
        provider_model_id="qwen/qwen3-235b-a22b-2507",
        label="Qwen3 235B A22B",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openrouter:deepseek-deepseek-r1": CuratedAiModelTemplate(
        template_id="openrouter:deepseek-deepseek-r1",
        provider="openrouter",
        provider_model_id="deepseek/deepseek-r1",
        label="DeepSeek R1",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    "openrouter:deepseek-deepseek-v3.2": CuratedAiModelTemplate(
        template_id="openrouter:deepseek-deepseek-v3.2",
        provider="openrouter",
        provider_model_id="deepseek/deepseek-v3.2",
        label="DeepSeek V3.2",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # --- Mistral ---
    "mistral:mistral-large-latest": CuratedAiModelTemplate(
        template_id="mistral:mistral-large-latest",
        provider="mistral",
        provider_model_id="mistral-large-latest",
        label="Mistral Large",
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    ),
    # --- OpenAI embeddings ---
    "openai:text-embedding-3-small": CuratedAiModelTemplate(
        template_id="openai:text-embedding-3-small",
        provider="openai",
        provider_model_id="text-embedding-3-small",
        label="text-embedding-3-small",
        capabilities=(AI_CAPABILITY_EMBEDDING,),
        model_kind=AI_MODEL_KIND_EMBEDDING,
    ),
    "openai:text-embedding-3-large": CuratedAiModelTemplate(
        template_id="openai:text-embedding-3-large",
        provider="openai",
        provider_model_id="text-embedding-3-large",
        label="text-embedding-3-large",
        capabilities=(AI_CAPABILITY_EMBEDDING,),
        model_kind=AI_MODEL_KIND_EMBEDDING,
    ),
}


class CuratedAiModelOptionOut(BaseModel):
    curated_id: str
    provider: str
    provider_model_id: str
    label: str
    model_kind: str
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
    litellm_model: str | None = None
    integration_secret_id: int | None = None
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
    """Create from a curated preset or a custom routed model with its own saved credential."""

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
    litellm_model: str | None = Field(
        default=None,
        description="Full LiteLLM model string for custom models (e.g. dashscope/qwen-turbo).",
    )
    integration_secret_id: int | None = Field(
        default=None,
        description="Saved credential id (organization integration secret); required for customs.",
    )
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
    litellm_model: str | None = None
    integration_secret_id: int | None = None


def list_curated_options_out() -> list[CuratedAiModelOptionOut]:
    templates = list(CURATED_TEMPLATES.values())
    return [
        CuratedAiModelOptionOut(
            curated_id=t.template_id,
            provider=t.provider,
            provider_model_id=t.provider_model_id,
            label=t.label,
            model_kind=t.model_kind,
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

    Keys follow LiteLLM's ``model_prices_and_context_window.json`` naming; see
    ``litellm_model_cost_lookup_keys``.
    """
    if litellm is None:
        return None

    model_cost = getattr(litellm, "model_cost", None)
    if not isinstance(model_cost, dict):
        return None
    for key in litellm_model_cost_lookup_keys(provider, provider_model_id):
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


def _validate_capabilities(caps: list[str], *, model_kind: str) -> list[str]:
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
    mk = _validate_model_kind(model_kind)
    if mk == AI_MODEL_KIND_EMBEDDING:
        if AI_CAPABILITY_EMBEDDING not in ordered:
            raise HTTPException(
                status_code=400,
                detail="Embedding models require the embedding capability",
            )
        extra = [c for c in ordered if c != AI_CAPABILITY_EMBEDDING]
        if extra:
            raise HTTPException(
                status_code=400,
                detail="Embedding models only support the embedding capability",
            )
    else:
        if AI_CAPABILITY_EMBEDDING in ordered:
            raise HTTPException(
                status_code=400,
                detail="Generative models cannot include the embedding capability",
            )
        if not any(
            c in (AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON, AI_CAPABILITY_VISION)
            for c in ordered
        ):
            raise HTTPException(
                status_code=400,
                detail="Generative models require at least one of text, json, or vision",
            )
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


def _split_litellm_route_for_storage(litellm_model: str) -> tuple[str, str]:
    """Derive legacy provider columns from a routing string (split on the first slash)."""
    s = litellm_model.strip()
    if not s:
        raise HTTPException(status_code=400, detail="litellm_model is empty")
    if len(s) > 512:
        raise HTTPException(status_code=400, detail="litellm_model is too long")
    if "/" in s:
        prov, rest = s.split("/", 1)
        p = prov.strip().lower()
        r = rest.strip()
        if not p or not r:
            raise HTTPException(
                status_code=400,
                detail="litellm_model must include both provider and model identifier",
            )
        return p, r
    return "openai", s


def row_to_out(row: BackfieldAiModelConfig) -> AiModelConfigOut:
    tested_at = row.latest_tested_at.isoformat() if row.latest_tested_at else None
    lm_raw = row.litellm_model
    lm_out = str(lm_raw).strip() if lm_raw else None
    sid = row.integration_secret_id
    sid_out = int(sid) if sid is not None else None
    return AiModelConfigOut(
        id=str(row.id),
        organization_id=int(row.organization_id),
        name=str(row.name),
        provider=str(row.provider),
        provider_model_id=str(row.provider_model_id),
        litellm_model=lm_out,
        integration_secret_id=sid_out,
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


def purge_org_model_config_session(
    session: Session, *, organization_id: int, config_id: str
) -> None:
    """Remove one catalog row in-session (no commit). Caller commits."""
    row = get_org_model_config(session, organization_id=organization_id, config_id=config_id)
    pk = row.id
    ov_where = BackfieldAiProjectModelOverride.model_config_id == pk
    for ov in session.exec(select(BackfieldAiProjectModelOverride).where(ov_where)).all():
        sid = ov.integration_secret_id
        if sid is not None:
            ov.integration_secret_id = None
            session.add(ov)
            session.flush()
            sec = session.get(BackfieldOrganizationIntegrationSecret, int(sid))
            if sec is not None:
                ik = str(sec.integration_key)
                if is_project_model_override_integration_key(ik):
                    session.delete(sec)
        session.delete(ov)
    dr_where = BackfieldAiDefaultModelRole.model_config_id == pk
    for dr in session.exec(select(BackfieldAiDefaultModelRole).where(dr_where)).all():
        session.delete(dr)
    cr_where = BackfieldAiCallRecord.model_config_id == pk
    for rec in session.exec(select(BackfieldAiCallRecord).where(cr_where)).all():
        rec.model_config_id = None
        session.add(rec)
    session.delete(row)


def delete_org_model_config(session: Session, *, organization_id: int, config_id: str) -> None:
    """Remove catalog row; clear overrides and default-role picks; detach call-record FK."""
    try:
        purge_org_model_config_session(
            session, organization_id=organization_id, config_id=config_id
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not remove this model (try again or contact support)",
        ) from None


def create_org_model_config(
    session: Session,
    organization_id: int,
    body: AiModelConfigCreateBody,
) -> AiModelConfigOut:
    currency = _normalize_currency(body.currency)
    inp_p, out_p = _validate_optional_prices(body.input_token_price, body.output_token_price)

    litellm_route: str | None = None
    integration_sid: int | None = None

    if body.curated_id:
        if (body.litellm_model or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Curated presets must not set litellm_model",
            )
        tmpl = CURATED_TEMPLATES.get(body.curated_id.strip())
        if tmpl is None:
            raise HTTPException(status_code=400, detail="Unknown curated_id")
        model_kind = _validate_model_kind(tmpl.model_kind)
        if "model_kind" in body.model_fields_set:
            body_mk = _validate_model_kind(body.model_kind)
            if body_mk != model_kind:
                raise HTTPException(
                    status_code=400,
                    detail="model_kind must match the curated template",
                )
        name = (body.name or tmpl.label).strip()
        provider = tmpl.provider.strip().lower()
        provider_model_id = tmpl.provider_model_id.strip()
        caps_raw = body.capabilities if body.capabilities is not None else list(tmpl.capabilities)
        sid_opt = body.integration_secret_id
        if sid_opt is not None:
            assert_integration_secret_assignable_for_catalog_model(
                session,
                organization_id,
                int(sid_opt),
            )
            integration_sid = int(sid_opt)
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
        if (body.provider or "").strip() or (body.provider_model_id or "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Use litellm_model and integration_secret_id for custom rows; "
                    "omit provider fields."
                ),
            )
        lm_in = (body.litellm_model or "").strip()
        cid_in = body.integration_secret_id
        if not lm_in:
            raise HTTPException(
                status_code=400,
                detail="litellm_model is required for custom models",
            )
        if cid_in is None:
            raise HTTPException(
                status_code=400,
                detail="integration_secret_id is required for custom models",
            )
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="name is required for custom models")
        if body.capabilities is None:
            raise HTTPException(
                status_code=400,
                detail="capabilities is required for custom models",
            )
        name = body.name.strip()
        litellm_route = lm_in
        assert_integration_secret_assignable_for_catalog_model(
            session,
            organization_id,
            int(cid_in),
        )
        provider, provider_model_id = _split_litellm_route_for_storage(litellm_route)
        integration_sid = int(cid_in)
        caps_raw = body.capabilities
        model_kind = _validate_model_kind(body.model_kind)

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    capabilities = _validate_capabilities(caps_raw, model_kind=model_kind)

    row = BackfieldAiModelConfig(
        organization_id=organization_id,
        name=name,
        provider=provider,
        provider_model_id=provider_model_id,
        litellm_model=litellm_route,
        integration_secret_id=integration_sid,
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

    if "model_kind" in data and data["model_kind"] is not None:
        row.model_kind = _validate_model_kind(str(data["model_kind"]))

    if "capabilities" in data:
        caps = data["capabilities"]
        if caps is None:
            raise HTTPException(status_code=400, detail="capabilities must not be null")
        row.capabilities_json = _validate_capabilities(
            list(caps),
            model_kind=str(row.model_kind),
        )

    if "config_json" in data:
        row.config_json = data["config_json"]

    if "currency" in data and data["currency"] is not None:
        row.currency = _normalize_currency(str(data["currency"]))

    if "model_kind" in data and "capabilities" not in data:
        row.capabilities_json = _validate_capabilities(
            list(row.capabilities_json or []),
            model_kind=str(row.model_kind),
        )

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

    if "litellm_model" in data:
        lm = str(data["litellm_model"]).strip()
        if not lm:
            raise HTTPException(status_code=400, detail="litellm_model must not be empty")
        if len(lm) > 512:
            raise HTTPException(status_code=400, detail="litellm_model is too long")
        if row.integration_secret_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only custom models that use a saved API credential can change routing."
                ),
            )
        row.litellm_model = lm
        row.provider, row.provider_model_id = _split_litellm_route_for_storage(lm)

    if "integration_secret_id" in data:
        new_raw = data["integration_secret_id"]
        if new_raw is None:
            raise HTTPException(status_code=400, detail="integration_secret_id cannot be cleared")
        try:
            new_sid = int(new_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="integration_secret_id must be an integer")
        if new_sid <= 0:
            raise HTTPException(status_code=400, detail="integration_secret_id must be positive")
        assert_integration_secret_assignable_for_catalog_model(
            session,
            organization_id,
            new_sid,
        )
        row.integration_secret_id = new_sid

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
    from backfield_ai.embeddings import EMBEDDING_CONNECTION_TEST_TEXT, embed_texts_sync

    row = get_org_model_config(session, organization_id=organization_id, config_id=config_id)
    is_embedding = str(row.model_kind) == AI_MODEL_KIND_EMBEDDING
    lm = effective_litellm_model_row(
        litellm_model=row.litellm_model,
        provider=str(row.provider),
        provider_model_id=str(row.provider_model_id),
    )
    api_key: str | None = None
    api_base: str | None = None

    sid = row.integration_secret_id
    if sid is not None:
        cred = session.get(BackfieldOrganizationIntegrationSecret, int(sid))
        if cred is None or int(cred.organization_id) != organization_id:
            raise HTTPException(
                status_code=400,
                detail="Saved API credential for this model was not found.",
            )
        try:
            api_key = decrypt_secret(cred.value_encrypted)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Could not decrypt saved API credential.",
            ) from None
        if not (api_key or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Saved API credential for this model is empty.",
            )
        api_base = (cred.api_base or "").strip() or None
    else:
        keys = organization_llm_api_keys(session, organization_id)
        prov = str(row.provider).strip().lower()
        if prov == "openai":
            api_key = keys.get("OPENAI_API_KEY")
        elif prov == "anthropic":
            api_key = keys.get("ANTHROPIC_API_KEY")
        elif prov == "gemini":
            api_key = keys.get("GEMINI_API_KEY")
        elif prov == "openrouter":
            api_key = keys.get("OPENROUTER_API_KEY")
        elif prov == "azure":
            api_key = keys.get("AZURE_API_KEY")
            api_base = os.getenv("AZURE_API_BASE")
        else:
            api_key = (
                keys.get("OPENAI_API_KEY")
                or keys.get("ANTHROPIC_API_KEY")
                or keys.get("GEMINI_API_KEY")
                or keys.get("OPENROUTER_API_KEY")
                or keys.get("AZURE_API_KEY")
            )

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No provider credentials configured for this organization",
        )
    low_lm = lm.strip().lower()
    if low_lm.startswith("azure/") and not (api_base or "").strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Azure OpenAI needs your resource endpoint URL on the Core API host "
                "for organization tests, as the credential on this model, "
                "or under each project's Integrations for flows."
            ),
        )

    now = datetime.now(UTC)
    try:
        if is_embedding:
            batch = embed_texts_sync(
                litellm_model=lm,
                texts=[EMBEDDING_CONNECTION_TEST_TEXT],
                api_key=api_key,
                api_base=api_base,
                timeout=60.0,
                track_attempt=False,
            )
            if batch.batch_error or not batch.items or batch.items[0].vector is None:
                raise RuntimeError(batch.batch_error or "Embedding test returned no vector")
        else:
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
                api_base=api_base,
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
