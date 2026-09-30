"""Organization platform integration secrets merge into worker env."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backfield_ai.constants import (
    INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH,
    INTEGRATION_KEY_PLATFORM_S3_ROLE_ARN,
)
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationIntegrationSecret,
    BackfieldProject,
    BackfieldProjectSecret,
)
from backfield_db.crypto import encrypt_secret
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine

from tests.project_helpers import project_ownership_fields


@pytest.fixture
def session_with_project(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", key)
    url = f"sqlite:///{tmp_path}/plat.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-plat")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        proj = BackfieldProject(
            **project_ownership_fields(session, oid), organization_id=oid, name="P", slug="p-plat"
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        yield session, oid, pid, now


def test_org_platform_pelias_visible(session_with_project):
    session, oid, pid, now = session_with_project
    session.add(
        BackfieldOrganizationIntegrationSecret(
            organization_id=oid,
            integration_key=INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH,
            value_encrypted=encrypt_secret("earth-key"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    env = merge_project_and_org_llm_api_keys(session, pid)
    assert env.get("PELIAS_API_KEY") == "earth-key"


def test_project_secret_overrides_org_platform(session_with_project):
    session, oid, pid, now = session_with_project
    session.add(
        BackfieldOrganizationIntegrationSecret(
            organization_id=oid,
            integration_key=INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH,
            value_encrypted=encrypt_secret("earth-key"),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        BackfieldProjectSecret(
            project_id=pid,
            key="PELIAS_API_KEY",
            value_encrypted=encrypt_secret("proj-key"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    env = merge_project_and_org_llm_api_keys(session, pid)
    assert env.get("PELIAS_API_KEY") == "proj-key"


def test_org_s3_role_arn_maps_to_backfield_env(session_with_project):
    session, oid, pid, now = session_with_project
    session.add(
        BackfieldOrganizationIntegrationSecret(
            organization_id=oid,
            integration_key=INTEGRATION_KEY_PLATFORM_S3_ROLE_ARN,
            value_encrypted=encrypt_secret("arn:aws:iam::1:role/org"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    env = merge_project_and_org_llm_api_keys(session, pid)
    assert env.get("BACKFIELD_S3_ROLE_ARN") == "arn:aws:iam::1:role/org"


def test_project_s3_role_arn_overrides_org(session_with_project):
    session, oid, pid, now = session_with_project
    session.add(
        BackfieldOrganizationIntegrationSecret(
            organization_id=oid,
            integration_key=INTEGRATION_KEY_PLATFORM_S3_ROLE_ARN,
            value_encrypted=encrypt_secret("arn:aws:iam::1:role/org"),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        BackfieldProjectSecret(
            project_id=pid,
            key="BACKFIELD_S3_ROLE_ARN",
            value_encrypted=encrypt_secret("arn:aws:iam::1:role/project"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    env = merge_project_and_org_llm_api_keys(session, pid)
    assert env.get("BACKFIELD_S3_ROLE_ARN") == "arn:aws:iam::1:role/project"
