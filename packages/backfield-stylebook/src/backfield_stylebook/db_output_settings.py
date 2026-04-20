"""Validated parameters for Stylebook Output (DBOutput) canonicalization."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import BackfieldProject, Stylebook
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id

CanonicalizationMode = Literal["rules", "ai_assisted"]
AdjudicationModel = Literal["gpt-5-nano", "gpt-5-mini"]


class DbOutputCanonicalSettings(BaseModel):
    """Canonicalization options persisted on the DBOutput node (params / React node.data)."""

    stylebook_id: int | None = Field(
        default=None,
        description="When set, canonical policy uses this Stylebook (same org as project). "
        "When null, use the project's workspace default Stylebook.",
    )
    canonicalization_mode: CanonicalizationMode = "rules"
    auto_apply_canonicalization: bool = True
    adjudication_model: AdjudicationModel = "gpt-5-nano"

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "stylebook_id" in out and out["stylebook_id"] == "":
            out["stylebook_id"] = None
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
    """Return Stylebook id for persistence, validating org ownership when override is set."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        msg = f"project {project_id} not found"
        raise ValueError(msg)
    oid = int(proj.organization_id)
    if stylebook_id_override is not None:
        sb = session.get(Stylebook, int(stylebook_id_override))
        if sb is None or sb.id is None:
            msg = f"stylebook {stylebook_id_override} not found"
            raise ValueError(msg)
        if int(sb.organization_id) != oid:
            msg = "stylebook does not belong to the project's organization"
            raise ValueError(msg)
        return int(sb.id)
    return resolve_stylebook_id_for_project_id(session, project_id)
