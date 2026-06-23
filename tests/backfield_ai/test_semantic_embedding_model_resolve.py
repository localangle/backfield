"""Resolve semantic.embedding and generative.default default model roles."""

from __future__ import annotations

import pytest
from backfield_ai.constants import (
    AI_DEFAULT_ROLE_GENERATIVE_DEFAULT,
    AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
    AI_DEFAULT_ROLE_SEMANTIC_HYDE,
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
)
from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.model_resolve import (
    resolve_generative_default_model_config_id,
    resolve_semantic_embedding_model_config_id,
    resolve_semantic_hyde_model_config_id,
    semantic_embedding_configured,
)
from backfield_db import (
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_resolve_semantic_embedding_model_prefers_project_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-res")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="emb-project",
            organization_id=org_id,
            name="Embed",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-emb", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
                model_config_id="emb-project",
            )
        )
        session.commit()

        assert (
            resolve_semantic_embedding_model_config_id(session, project_id) == "emb-project"
        )


def test_resolve_semantic_embedding_model_missing_raises() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-miss")
        session.add(org)
        session.commit()
        session.refresh(org)
        proj = BackfieldProject(
            name="P",
            slug="p-emb-miss",
            organization_id=int(org.id),  # type: ignore[arg-type]
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)

        with pytest.raises(EmbeddingConfigurationError, match="No embedding model configured"):
            resolve_semantic_embedding_model_config_id(session, int(proj.id))


def test_semantic_embedding_configured_false_without_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-cfg0")
        session.add(org)
        session.commit()
        session.refresh(org)
        proj = BackfieldProject(
            name="P",
            slug="p-emb-cfg0",
            organization_id=int(org.id),  # type: ignore[arg-type]
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]

        assert semantic_embedding_configured(session, project_id) is False


def test_semantic_embedding_configured_false_when_project_default_disabled() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-cfg-off")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="emb-off",
            organization_id=org_id,
            name="Embed",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-emb-off", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
                model_config_id="emb-off",
            )
        )
        session.add(
            BackfieldAiProjectModelOverride(
                project_id=project_id,
                model_config_id="emb-off",
                enabled=False,
            )
        )
        session.commit()

        assert semantic_embedding_configured(session, project_id) is False


def test_semantic_embedding_configured_true_with_enabled_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-cfg-on")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="emb-on",
            organization_id=org_id,
            name="Embed",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-emb-on", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
                model_config_id="emb-on",
            )
        )
        session.commit()

        assert semantic_embedding_configured(session, project_id) is True


def test_resolve_semantic_embedding_uses_sole_enabled_when_default_points_off() -> None:
    """Project default may still reference a model turned off for this project."""
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-sole")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg_off = BackfieldAiModelConfig(
            id="emb-off-default",
            organization_id=org_id,
            name="Embed off",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        cfg_on = BackfieldAiModelConfig(
            id="emb-on-sole",
            organization_id=org_id,
            name="Embed on",
            provider="openai",
            provider_model_id="text-embedding-3-large",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        session.add(cfg_off)
        session.add(cfg_on)
        proj = BackfieldProject(name="P", slug="p-emb-sole", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
                model_config_id="emb-off-default",
            )
        )
        session.add(
            BackfieldAiProjectModelOverride(
                project_id=project_id,
                model_config_id="emb-off-default",
                enabled=False,
            )
        )
        session.commit()

        assert (
            resolve_semantic_embedding_model_config_id(session, project_id) == "emb-on-sole"
        )
        assert semantic_embedding_configured(session, project_id) is True


def test_resolve_semantic_embedding_after_default_re_enabled() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-emb-reon")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="emb-reon",
            organization_id=org_id,
            name="Embed",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            model_kind=AI_MODEL_KIND_EMBEDDING,
            capabilities_json=["embedding"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-emb-reon", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
                model_config_id="emb-reon",
            )
        )
        session.add(
            BackfieldAiProjectModelOverride(
                project_id=project_id,
                model_config_id="emb-reon",
                enabled=False,
            )
        )
        session.commit()
        assert semantic_embedding_configured(session, project_id) is False

        ovr = session.exec(
            select(BackfieldAiProjectModelOverride).where(
                BackfieldAiProjectModelOverride.project_id == project_id,
            )
        ).one()
        ovr.enabled = True
        session.add(ovr)
        session.commit()

        assert resolve_semantic_embedding_model_config_id(session, project_id) == "emb-reon"
        assert semantic_embedding_configured(session, project_id) is True


def test_resolve_generative_default_prefers_project_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-gen-res")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="gen-project-default",
            organization_id=org_id,
            name="Generative",
            provider="openai",
            provider_model_id="gpt-4o-mini",
            model_kind=AI_MODEL_KIND_GENERATIVE,
            capabilities_json=["text"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-gen-res", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_GENERATIVE_DEFAULT,
                model_config_id="gen-project-default",
            )
        )
        session.commit()

        assert (
            resolve_generative_default_model_config_id(session, project_id) == "gen-project-default"
        )
        assert (
            resolve_semantic_hyde_model_config_id(session, project_id) == "gen-project-default"
        )


def test_resolve_generative_default_falls_back_to_legacy_semantic_hyde_role() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-hyde-legacy")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="gen-hyde-legacy",
            organization_id=org_id,
            name="HyDE legacy",
            provider="openai",
            provider_model_id="gpt-4o-mini",
            model_kind=AI_MODEL_KIND_GENERATIVE,
            capabilities_json=["text"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-hyde-legacy", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiDefaultModelRole(
                project_id=project_id,
                organization_id=None,
                role=AI_DEFAULT_ROLE_SEMANTIC_HYDE,
                model_config_id="gen-hyde-legacy",
            )
        )
        session.commit()

        assert (
            resolve_generative_default_model_config_id(session, project_id) == "gen-hyde-legacy"
        )


def test_resolve_generative_default_uses_sole_enabled_generative_when_no_default() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-hyde-sole")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        cfg = BackfieldAiModelConfig(
            id="gen-hyde-sole",
            organization_id=org_id,
            name="HyDE sole",
            provider="openai",
            provider_model_id="gpt-4o-mini",
            model_kind=AI_MODEL_KIND_GENERATIVE,
            capabilities_json=["text"],
        )
        session.add(cfg)
        proj = BackfieldProject(name="P", slug="p-hyde-sole", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]

        assert resolve_generative_default_model_config_id(session, project_id) == "gen-hyde-sole"


def test_resolve_generative_default_missing_raises() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-hyde-miss")
        session.add(org)
        session.commit()
        session.refresh(org)
        proj = BackfieldProject(
            name="P",
            slug="p-hyde-miss",
            organization_id=int(org.id),  # type: ignore[arg-type]
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)

        with pytest.raises(EmbeddingConfigurationError, match="No generative model configured"):
            resolve_generative_default_model_config_id(session, int(proj.id))
