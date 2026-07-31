"""Public project keys are valid only while their principals retain access."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from backfield_auth.gate import try_resolve_bearer_api_key
from backfield_db import (
    BackfieldApiCredential,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    Stylebook,
)
from sqlmodel import Session, SQLModel, create_engine, select

RAW_KEY = "bfk_personal_lifecycle_key_1234567890abcdef"


def _seed_personal_key() -> tuple[Session, BackfieldApiCredential]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    organization = BackfieldOrganization(name="Newsroom", slug="newsroom")
    session.add(organization)
    session.flush()
    stylebook = Stylebook(
        organization_id=int(organization.id),
        name="Default",
        slug="default",
        is_default=True,
    )
    session.add(stylebook)
    session.flush()
    workspace = BackfieldWorkspace(
        organization_id=int(organization.id),
        stylebook_id=int(stylebook.id),
        name="Default",
        slug="default",
    )
    session.add(workspace)
    session.flush()
    project = BackfieldProject(
        organization_id=int(organization.id),
        workspace_id=int(workspace.id),
        stylebook_id=int(stylebook.id),
        name="Reporting",
        slug="reporting",
    )
    user = BackfieldUser(email="reporter@example.com", password_hash="unused")
    session.add(project)
    session.add(user)
    session.flush()
    session.add(
        BackfieldOrganizationMembership(
            user_id=int(user.id),
            organization_id=int(organization.id),
            role="member",
        )
    )
    session.add(
        BackfieldWorkspaceMembership(
            user_id=int(user.id),
            workspace_id=int(workspace.id),
        )
    )
    credential = BackfieldApiCredential(
        project_id=int(project.id),
        user_id=int(user.id),
        credential_type="user",
        key_prefix=RAW_KEY[:22],
        key_hash=hashlib.sha256(RAW_KEY.encode()).hexdigest(),
        scopes="read",
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return session, credential


def test_active_personal_key_resolves_bound_project_and_organization() -> None:
    session, credential = _seed_personal_key()
    try:
        auth = try_resolve_bearer_api_key(session, RAW_KEY)
        assert auth is not None
        assert auth["project_id"] == credential.project_id
        assert auth["organization_id"] == 1
    finally:
        session.close()


def test_disabled_owner_invalidates_personal_key() -> None:
    session, credential = _seed_personal_key()
    try:
        owner = session.get(BackfieldUser, int(credential.user_id))
        assert owner is not None
        owner.disabled_at = datetime.now(UTC)
        session.add(owner)
        session.commit()
        assert try_resolve_bearer_api_key(session, RAW_KEY) is None
    finally:
        session.close()


def test_removed_organization_membership_invalidates_personal_key() -> None:
    session, _credential = _seed_personal_key()
    try:
        membership = session.exec(select(BackfieldOrganizationMembership)).one()
        session.delete(membership)
        session.commit()
        assert try_resolve_bearer_api_key(session, RAW_KEY) is None
    finally:
        session.close()


def test_removed_project_access_invalidates_personal_key() -> None:
    session, _credential = _seed_personal_key()
    try:
        membership = session.exec(select(BackfieldWorkspaceMembership)).one()
        session.delete(membership)
        session.commit()
        assert try_resolve_bearer_api_key(session, RAW_KEY) is None
    finally:
        session.close()


def test_revoked_personal_key_is_retained_but_invalid() -> None:
    session, credential = _seed_personal_key()
    try:
        credential.revoked_at = datetime.now(UTC)
        session.add(credential)
        session.commit()
        assert session.get(BackfieldApiCredential, int(credential.id)) is not None
        assert try_resolve_bearer_api_key(session, RAW_KEY) is None
    finally:
        session.close()


def test_ownerless_personal_key_fails_closed() -> None:
    session, credential = _seed_personal_key()
    try:
        credential.user_id = None
        session.add(credential)
        session.commit()
        assert try_resolve_bearer_api_key(session, RAW_KEY) is None
    finally:
        session.close()


def test_ownerless_service_key_is_explicit_trusted_legacy_path() -> None:
    session, credential = _seed_personal_key()
    try:
        credential.user_id = None
        credential.credential_type = "service"
        session.add(credential)
        session.commit()
        auth = try_resolve_bearer_api_key(session, RAW_KEY)
        assert auth is not None
        assert auth["credential_type"] == "service"
    finally:
        session.close()
