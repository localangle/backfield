"""Resolve semantic.embedding default model role."""

from __future__ import annotations

import pytest
from backfield_ai.constants import AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING, AI_MODEL_KIND_EMBEDDING
from backfield_ai.embeddings import EmbeddingConfigurationError
from backfield_ai.model_resolve import resolve_semantic_embedding_model_config_id
from backfield_db import (
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlmodel import Session, SQLModel, create_engine


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
