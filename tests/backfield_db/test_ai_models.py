"""Schema contract tests for shared Backfield AI models."""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from backfield_db import (
    BackfieldAiCallRecord,
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldOrganizationIntegrationSecret,
)
from sqlalchemy import CheckConstraint, Numeric, UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def _check_constraint_names(model: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _index_names(model: type[object]) -> set[str]:
    return {index.name for index in model.__table__.indexes}


def test_ai_table_names_use_shared_backfield_prefix() -> None:
    assert BackfieldAiModelConfig.__tablename__ == "backfield_ai_model_config"
    assert BackfieldAiProjectModelOverride.__tablename__ == "backfield_ai_project_model_override"
    assert BackfieldAiDefaultModelRole.__tablename__ == "backfield_ai_default_model_role"
    assert BackfieldAiCallRecord.__tablename__ == "backfield_ai_call_record"


def test_organization_integration_secret_org_scoped_keys() -> None:
    assert BackfieldOrganizationIntegrationSecret.__tablename__ == (
        "backfield_organization_integration_secret"
    )
    assert _unique_constraint_columns(
        BackfieldOrganizationIntegrationSecret,
        "uq_backfield_org_integration_secret_org_key",
    ) == ("organization_id", "integration_key")
    assert (
        "ix_backfield_organization_integration_secret_organization_id"
        in _index_names(BackfieldOrganizationIntegrationSecret)
    )


def test_model_config_defaults_and_decimal_pricing_fields() -> None:
    first = BackfieldAiModelConfig(
        organization_id=1,
        name="GPT Mini",
        provider="openai",
        provider_model_id="gpt-5-mini",
        input_token_price=Decimal("0.000001250000"),
    )
    second = BackfieldAiModelConfig(
        organization_id=1,
        name="Claude",
        provider="anthropic",
        provider_model_id="claude-sonnet",
    )

    first.capabilities_json.append("json")

    assert first.model_kind == "generative"
    assert first.status == "active"
    assert first.currency == "USD"
    assert first.input_token_price == Decimal("0.000001250000")
    assert second.capabilities_json == []

    input_price = BackfieldAiModelConfig.__table__.c.input_token_price.type
    output_price = BackfieldAiModelConfig.__table__.c.output_token_price.type
    assert isinstance(input_price, Numeric)
    assert input_price.precision == 18
    assert input_price.scale == 12
    assert isinstance(output_price, Numeric)
    assert output_price.precision == 18
    assert output_price.scale == 12


def test_model_config_constraints_and_indexes_cover_catalog_lookup_paths() -> None:
    assert _unique_constraint_columns(
        BackfieldAiModelConfig,
        "uq_backfield_ai_model_config_org_name",
    ) == ("organization_id", "name")

    indexes = _index_names(BackfieldAiModelConfig)
    assert "ix_backfield_ai_model_config_org_provider_model" in indexes
    assert "ix_backfield_ai_model_config_org_status_kind" in indexes


def test_project_override_is_unique_per_project_model() -> None:
    assert _unique_constraint_columns(
        BackfieldAiProjectModelOverride,
        "uq_backfield_ai_project_model_override_project_model",
    ) == ("project_id", "model_config_id")
    assert "ix_backfield_ai_project_model_override_project_enabled" in _index_names(
        BackfieldAiProjectModelOverride
    )


def test_default_model_role_requires_exactly_one_scope_and_indexes_roles() -> None:
    assert "ck_backfield_ai_default_model_role_one_scope" in _check_constraint_names(
        BackfieldAiDefaultModelRole
    )

    indexes = _index_names(BackfieldAiDefaultModelRole)
    assert "uq_backfield_ai_default_model_role_org_role" in indexes
    assert "uq_backfield_ai_default_model_role_project_role" in indexes


def test_call_record_tracks_cost_context_without_prompt_or_response_content() -> None:
    record = BackfieldAiCallRecord(
        project_id=1,
        provider="openai",
        provider_model_id="gpt-5-mini",
        status="succeeded",
        estimated_cost=Decimal("0.000420000000"),
    )

    assert record.model_kind == "generative"
    assert record.attempt_number == 1
    assert record.currency == "USD"
    assert record.cost_estimate_incomplete is False
    assert record.estimated_cost == Decimal("0.000420000000")

    columns = set(BackfieldAiCallRecord.__table__.c.keys())
    assert "prompt" not in columns
    assert "prompt_text" not in columns
    assert "response" not in columns
    assert "response_text" not in columns

    estimated_cost = BackfieldAiCallRecord.__table__.c.estimated_cost.type
    assert isinstance(estimated_cost, Numeric)
    assert estimated_cost.precision == 18
    assert estimated_cost.scale == 12

    indexes = _index_names(BackfieldAiCallRecord)
    assert "ix_backfield_ai_call_record_project_created" in indexes
    assert "ix_backfield_ai_call_record_run_node" in indexes
    assert "ix_backfield_ai_call_record_run_status" in indexes


def test_backfield_ai_import_does_not_pull_in_agate_or_worker_modules() -> None:
    script = """
import sys

import backfield_ai

assert backfield_ai.DEFAULT_AI_CURRENCY == "USD"
for name in ("backfield_core", "backfield_agate", "worker.tasks"):
    assert name not in sys.modules, name
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        env={"PYTHONPATH": str(Path("packages/backfield-ai/src").resolve())},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
