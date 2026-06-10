"""Alembic environment."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from backfield_db.article_embedding_models import SubstrateArticleEmbedding  # noqa: F401
from backfield_db.models import (  # noqa: F401
    AgateGraph,
    AgateRun,
    AgateTemplate,
    BackfieldAiCallRecord,
    BackfieldAiDefaultModelRole,
    BackfieldAiModelConfig,
    BackfieldAiProjectModelOverride,
    BackfieldApiCredential,
    BackfieldOrganization,
    BackfieldOrganizationIntegrationSecret,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldProjectSecret,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    Stylebook,
    StylebookBundleJob,
    StylebookMembership,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstrateArticle,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_db.semantic_document_models import (  # noqa: F401
    SubstrateLocationSemanticDocument,
    SubstratePersonSemanticDocument,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    return os.environ.get(
        "BACKFIELD_DATABASE_URL",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/backfield"),
    )


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
