"""Validated parameters for Backfield Output (DBOutput) canonicalization."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import BackfieldProject
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from backfield_entities.catalog.resolve import resolve_effective_stylebook_id_for_project

CanonicalizationMode = Literal["rules", "ai_assisted"]
ReconciliationPolicy = Literal["add_only", "smart_merge", "replace"]


class DbOutputCanonicalSettings(BaseModel):
    """Canonicalization options persisted on the DBOutput node (params / React node.data)."""

    stylebook_matching_enabled: bool = Field(
        default=True,
        description="When false, persist places without catalog linking or resolution.",
    )
    stylebook_id: int | None = Field(
        default=None,
        description="When set, canonical policy uses this Stylebook (same org as project). "
        "When null, use the organization's default Stylebook.",
    )
    canonicalization_mode: CanonicalizationMode = "ai_assisted"
    reconciliation_policy: ReconciliationPolicy = Field(
        default="smart_merge",
        description="How Backfield Output reconciles saved data in domains produced by this flow.",
    )
    auto_apply_canonicalization: bool = True
    adjudication_model: str = Field(
        default="gpt-5-nano",
        description="Provider model id for AI-assisted adjudication (legacy default when unset).",
    )
    adjudication_ai_model_config_id: str | None = Field(
        default=None,
        description="Optional Backfield AI catalog row id for credentials / LiteLLM routing.",
    )
    semantic_indexing_enabled: bool = Field(
        default=False,
        description="When true, Backfield Output synchronizes semantic search documents "
        "after substrate persistence.",
    )
    auto_connections_enabled: bool = Field(
        default=True,
        description="When true and canonicalization is AI-assisted with auto-apply, "
        "Backfield Output infers high-confidence Stylebook connections after persistence.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "stylebook_id" in out and out["stylebook_id"] == "":
            out["stylebook_id"] = None
        policy = out.get("reconciliation_policy")
        if isinstance(policy, str) and policy.strip() == "":
            out.pop("reconciliation_policy", None)
        am = out.get("adjudication_model")
        if isinstance(am, str) and am.strip() == "":
            out.pop("adjudication_model", None)
        return out

    @classmethod
    def from_node_params(cls, raw: dict[str, Any] | None) -> DbOutputCanonicalSettings:
        if not raw:
            return cls()
        return cls.model_validate(raw)


def resolve_effective_stylebook_id(
    session: Session,
    *,
    project_id: int,
    stylebook_id_override: int | None,
) -> int:
    """Return catalog id for DBOutput persistence (node override, else org default).

    Delegates to :func:`resolve_effective_stylebook_id_for_project` so precedence matches
    the documented bridge order (explicit id → slug — unused here — → organization default).
    """
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        msg = f"project {project_id} not found"
        raise ValueError(msg)
    return resolve_effective_stylebook_id_for_project(
        session,
        proj,
        stylebook_slug=None,
        catalog_stylebook_id=stylebook_id_override,
    )
