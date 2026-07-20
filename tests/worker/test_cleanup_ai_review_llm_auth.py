"""Tests for Stylebook cleanup AI review LLM credential resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.constants import INTEGRATION_KEY_AI_PROVIDER_OPENAI
from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldOrganizationIntegrationSecret,
    BackfieldProject,
)
from backfield_db.crypto import encrypt_secret
from backfield_entities.quality.cleanup_ai_review import CleanupClusterMember
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate.cleanup.ai_review import propose_for_cluster, run_cluster_partition_llm
from worker.substrate.cleanup.cleanup_llm_auth import (
    call_llm_kwargs_from_overlay,
    is_llm_auth_error,
    resolve_cleanup_llm_auth,
)


@pytest.fixture
def session_with_org(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", key)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    url = f"sqlite:///{tmp_path}/cleanup_llm_auth.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Cleanup Org", slug="cleanup-org")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        proj = BackfieldProject(organization_id=oid, name="P", slug="cleanup-proj")
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        yield session, oid, pid, now


def _add_openai_secret(session: Session, *, oid: int, now: datetime, value: str) -> int:
    secret = BackfieldOrganizationIntegrationSecret(
        organization_id=oid,
        integration_key=INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        value_encrypted=encrypt_secret(value),
        created_at=now,
        updated_at=now,
    )
    session.add(secret)
    session.commit()
    session.refresh(secret)
    return int(secret.id)  # type: ignore[arg-type]


def test_resolve_cleanup_llm_auth_uses_model_config_secret_without_env(
    session_with_org, monkeypatch
) -> None:
    session, oid, _pid, now = session_with_org
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret_id = _add_openai_secret(session, oid=oid, now=now, value="sk-from-catalog")
    cfg = BackfieldAiModelConfig(
        organization_id=oid,
        name="Cleanup GPT",
        provider="openai",
        provider_model_id="gpt-5-nano",
        model_kind="generative",
        status="active",
        capabilities_json=["text", "json"],
        litellm_model="openai/gpt-5-nano",
        integration_secret_id=secret_id,
    )
    session.add(cfg)
    session.commit()
    session.refresh(cfg)

    auth = resolve_cleanup_llm_auth(
        session,
        organization_id=oid,
        provider_model_id="gpt-5-nano",
        ai_model_config_id=str(cfg.id),
        default_model="gpt-5-nano",
    )

    assert auth.api_key_overlay.get("OPENAI_API_KEY") == "sk-from-catalog"
    assert call_llm_kwargs_from_overlay(auth.api_key_overlay)["openai_api_key"] == (
        "sk-from-catalog"
    )
    assert auth.model == "gpt-5-nano"
    assert auth.model_config_id == str(cfg.id)


def test_resolve_cleanup_llm_auth_fails_without_credentials(session_with_org) -> None:
    session, oid, _pid, _now = session_with_org
    with pytest.raises(ValueError, match="No provider credentials"):
        resolve_cleanup_llm_auth(
            session,
            organization_id=oid,
            provider_model_id="gpt-5-nano",
            ai_model_config_id=None,
            default_model="gpt-5-nano",
        )


def test_resolve_cleanup_llm_auth_fails_for_missing_model_config(session_with_org) -> None:
    session, oid, _pid, now = session_with_org
    _add_openai_secret(session, oid=oid, now=now, value="sk-org")
    with pytest.raises(ValueError, match="missing or belongs"):
        resolve_cleanup_llm_auth(
            session,
            organization_id=oid,
            provider_model_id="gpt-5-nano",
            ai_model_config_id="does-not-exist",
            default_model="gpt-5-nano",
        )


def test_run_cluster_partition_llm_passes_overlay_keys() -> None:
    with patch(
        "worker.substrate.cleanup.ai_review.call_llm",
        return_value='{"groups": []}',
    ) as mock_call:
        data = run_cluster_partition_llm(
            prompt="partition",
            model="gpt-5-nano",
            model_config_id="cfg-1",
            api_key_overlay={"OPENAI_API_KEY": "sk-overlay"},
        )
    assert data == {"groups": []}
    assert mock_call.call_args.kwargs["openai_api_key"] == "sk-overlay"
    assert mock_call.call_args.kwargs["model_config_id"] == "cfg-1"


def test_run_cluster_partition_llm_raises_when_overlay_empty() -> None:
    with pytest.raises(ValueError, match="No provider credentials"):
        run_cluster_partition_llm(
            prompt="partition",
            model="gpt-5-nano",
            model_config_id=None,
            api_key_overlay={},
        )


def test_propose_for_cluster_rethrows_auth_errors() -> None:
    members = [
        CleanupClusterMember(id="a", label="A", linked_substrate_count=1, mention_count=0),
        CleanupClusterMember(id="b", label="B", linked_substrate_count=1, mention_count=0),
    ]
    with patch(
        "worker.substrate.cleanup.ai_review.run_cluster_partition_llm",
        side_effect=ValueError("OPENAI_API_KEY must be provided (configure in project settings)"),
    ):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            propose_for_cluster(
                check_id="duplicate-people",
                members=members,
                model="gpt-5-nano",
                model_config_id=None,
                api_key_overlay={"OPENAI_API_KEY": "unused"},
            )


def test_propose_for_cluster_soft_fails_non_auth_errors() -> None:
    members = [
        CleanupClusterMember(id="a", label="A", linked_substrate_count=1, mention_count=0),
        CleanupClusterMember(id="b", label="B", linked_substrate_count=1, mention_count=0),
    ]
    with patch(
        "worker.substrate.cleanup.ai_review.run_cluster_partition_llm",
        side_effect=RuntimeError("temporary upstream blip"),
    ):
        drafts = propose_for_cluster(
            check_id="duplicate-people",
            members=members,
            model="gpt-5-nano",
            model_config_id=None,
            api_key_overlay={"OPENAI_API_KEY": "sk"},
        )
    assert drafts == []


def test_is_llm_auth_error_detects_missing_key() -> None:
    assert is_llm_auth_error(ValueError("OPENAI_API_KEY must be provided"))
    assert not is_llm_auth_error(RuntimeError("timeout after 30s"))


def test_execute_cleanup_ai_review_fails_loudly_when_auth_missing() -> None:
    from worker.tasks import execute_cleanup_ai_review

    review = MagicMock()
    review.status = "queued"
    review.stylebook_id = 1
    review.check_id = "duplicate-people"
    review.provider_model_id = "gpt-5-nano"
    review.ai_model_config_id = None

    stylebook = MagicMock()
    stylebook.organization_id = 9

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    def _get(model, key):  # noqa: ANN001
        if model.__name__ == "StylebookCleanupAiReview":
            return review
        if model.__name__ == "Stylebook":
            return stylebook
        return None

    session.get.side_effect = _get

    with (
        patch("worker.tasks.get_engine", return_value=MagicMock()),
        patch("worker.tasks.Session", return_value=session),
        patch(
            "worker.substrate.cleanup.cleanup_llm_auth.resolve_cleanup_llm_auth",
            side_effect=ValueError(
                "No provider credentials configured for this organization. "
                "Add AI credentials in organization settings before running this review."
            ),
        ),
        patch("worker.tasks._fail_cleanup_ai_review") as fail,
        patch("worker.tasks.run_cleanup_review_clusters") as run_clusters,
    ):
        execute_cleanup_ai_review("review-auth-fail")

    fail.assert_called_once()
    assert "No provider credentials" in fail.call_args.args[2]
    run_clusters.assert_not_called()
