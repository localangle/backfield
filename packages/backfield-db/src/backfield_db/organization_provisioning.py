"""Atomic, idempotent provisioning for a complete Backfield organization."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backfield_db.curated_ai_models import (
    CURATED_TEMPLATES,
    CuratedAiModelTemplate,
)
from backfield_db.models import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_db.passwords import hash_password, validate_password_strength
from backfield_db.session import create_direct_engine
from backfield_db.users import normalize_user_email, users_by_normalized_email

ORG_ADMIN_ROLE = "org_admin"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationProvisioningConflict(ValueError):
    """Existing state does not exactly match the requested starter organization."""


class StarterResourceInput(BaseModel):
    """Explicit name and stable slug for one starter resource."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        cleaned = value.strip()
        if not _SLUG_RE.fullmatch(cleaned):
            raise ValueError(
                "slug must contain lowercase letters, numbers, and single hyphens only"
            )
        return cleaned


class OrganizationProvisioningRequest(BaseModel):
    """Non-secret boundary contract for starter organization provisioning."""

    model_config = ConfigDict(extra="forbid", strict=True)

    organization: StarterResourceInput
    stylebook: StarterResourceInput
    workspace: StarterResourceInput
    project: StarterResourceInput
    client_admin_email: str = Field(min_length=1, max_length=320)
    support_admin_email: str | None = Field(default=None, max_length=320)
    curated_model_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("client_admin_email", "support_admin_email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or _EMAIL_RE.fullmatch(normalized) is None:
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("curated_model_ids")
    @classmethod
    def validate_model_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(model_id.strip() for model_id in value)
        if any(not model_id for model_id in normalized):
            raise ValueError("curated model ids must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("curated model ids must be unique")
        unknown = sorted(set(normalized) - CURATED_TEMPLATES.keys())
        if unknown:
            raise ValueError(f"Unknown curated model ids: {', '.join(unknown)}")
        return normalized

    @model_validator(mode="after")
    def validate_admins_are_distinct(self) -> OrganizationProvisioningRequest:
        if self.support_admin_email == self.client_admin_email:
            raise ValueError("support admin email must differ from client admin email")
        return self


class TemporaryPasswordInput(BaseModel):
    """Secret JSON file contract used only when provisioning creates users."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )

    client_admin_password: SecretStr = Field(min_length=8, max_length=128)
    support_admin_password: SecretStr | None = Field(
        default=None,
        min_length=8,
        max_length=128,
    )

class ProvisionedUserReport(BaseModel):
    email: str
    user_id: int
    created: bool
    membership_created: bool


class OrganizationProvisioningReport(BaseModel):
    organization_id: int
    organization_slug: str
    organization_created: bool
    stylebook_id: int
    stylebook_created: bool
    workspace_id: int
    workspace_created: bool
    project_id: int
    project_created: bool
    users: tuple[ProvisionedUserReport, ...]
    curated_model_ids: tuple[str, ...]
    model_config_ids: tuple[str, ...]

    @property
    def reused(self) -> bool:
        return not any(
            (
                self.organization_created,
                self.stylebook_created,
                self.workspace_created,
                self.project_created,
                *(user.created or user.membership_created for user in self.users),
            )
        )

    def to_json(self) -> str:
        return self.model_dump_json()


def load_temporary_passwords(path: str | Path) -> TemporaryPasswordInput:
    """Read a caller-owned JSON password file without modifying or exposing it."""
    password_path = Path(path)
    try:
        raw = password_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Could not read temporary password file: {password_path}") from exc
    try:
        return TemporaryPasswordInput.model_validate_json(raw)
    except ValueError as exc:
        raise ValueError(
            "Temporary password file must be valid JSON with "
            "client_admin_password and optional support_admin_password fields"
        ) from exc


def _required_id(row: object, resource: str) -> int:
    row_id = getattr(row, "id", None)
    if row_id is None:
        raise RuntimeError(f"{resource} row is missing an id after flush")
    return int(row_id)


def _conflict(message: str) -> OrganizationProvisioningConflict:
    return OrganizationProvisioningConflict(message)


def _require_resource_match(
    *,
    resource: str,
    actual_name: str,
    expected_name: str,
) -> None:
    if actual_name != expected_name:
        raise _conflict(
            f"Existing {resource} name {actual_name!r} does not match {expected_name!r}"
        )


def _get_exact_starter_resources(
    session: Session,
    request: OrganizationProvisioningRequest,
    organization: BackfieldOrganization,
) -> tuple[Stylebook, BackfieldWorkspace, BackfieldProject]:
    organization_id = _required_id(organization, "organization")
    stylebook = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == organization_id,
            Stylebook.slug == request.stylebook.slug,
        )
    ).first()
    if stylebook is None:
        raise _conflict("Existing organization is missing the requested Stylebook")
    _require_resource_match(
        resource="Stylebook",
        actual_name=str(stylebook.name),
        expected_name=request.stylebook.name,
    )
    if not bool(stylebook.is_default):
        raise _conflict("Existing starter Stylebook is not the organization default")

    stylebook_id = _required_id(stylebook, "Stylebook")
    workspace = session.exec(
        select(BackfieldWorkspace).where(
            BackfieldWorkspace.organization_id == organization_id,
            BackfieldWorkspace.slug == request.workspace.slug,
        )
    ).first()
    if workspace is None:
        raise _conflict("Existing organization is missing the requested workspace")
    _require_resource_match(
        resource="workspace",
        actual_name=str(workspace.name),
        expected_name=request.workspace.name,
    )
    if int(workspace.stylebook_id) != stylebook_id:
        raise _conflict("Existing workspace belongs to a different Stylebook")

    workspace_id = _required_id(workspace, "workspace")
    project = session.exec(
        select(BackfieldProject).where(
            BackfieldProject.organization_id == organization_id,
            BackfieldProject.slug == request.project.slug,
        )
    ).first()
    if project is None:
        raise _conflict("Existing organization is missing the requested project")
    _require_resource_match(
        resource="project",
        actual_name=str(project.name),
        expected_name=request.project.name,
    )
    if int(project.workspace_id) != workspace_id:
        raise _conflict("Existing project belongs to a different workspace")
    if int(project.stylebook_id) != stylebook_id:
        raise _conflict("Existing project belongs to a different Stylebook")
    return stylebook, workspace, project


def _model_matches_template(
    row: BackfieldAiModelConfig,
    template: CuratedAiModelTemplate,
) -> bool:
    return all(
        (
            str(row.name) == template.label,
            str(row.provider) == template.provider,
            str(row.provider_model_id) == template.provider_model_id,
            str(row.model_kind) == template.model_kind,
            str(row.status) == "active",
            list(row.capabilities_json or []) == list(template.capabilities),
            row.litellm_model is None,
            row.integration_secret_id is None,
            row.config_json is None,
            row.input_token_price is None,
            row.output_token_price is None,
            str(row.currency) == "USD",
        )
    )


def _validate_existing_models(
    session: Session,
    *,
    organization_id: int,
    selected_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rows = session.exec(
        select(BackfieldAiModelConfig)
        .where(BackfieldAiModelConfig.organization_id == organization_id)
        .order_by(col(BackfieldAiModelConfig.name))
    ).all()
    expected = {CURATED_TEMPLATES[model_id].label: model_id for model_id in selected_ids}
    if len(rows) != len(expected):
        raise _conflict(
            "Existing organization AI catalog does not match the requested curated snapshot"
        )
    model_config_ids: list[str] = []
    for row in rows:
        model_id = expected.get(str(row.name))
        if model_id is None or not _model_matches_template(row, CURATED_TEMPLATES[model_id]):
            raise _conflict(
                "Existing organization AI catalog does not match the requested curated snapshot"
            )
        model_config_ids.append(str(row.id))
    return tuple(model_config_ids)


def _validate_existing_admin(
    session: Session,
    *,
    organization_id: int,
    email: str,
) -> ProvisionedUserReport:
    user = _find_user_by_normalized_email(session, email)
    if user is None:
        raise _conflict(f"Existing organization is missing administrator {email}")
    if user.disabled_at is not None:
        raise _conflict(f"Existing administrator {email} is disabled")
    user_id = _required_id(user, "user")
    membership = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.organization_id == organization_id,
            BackfieldOrganizationMembership.user_id == user_id,
        )
    ).first()
    if membership is None or str(membership.role) != ORG_ADMIN_ROLE:
        raise _conflict(f"Existing administrator {email} does not have the org_admin role")
    return ProvisionedUserReport(
        email=email,
        user_id=user_id,
        created=False,
        membership_created=False,
    )


def _find_user_by_normalized_email(session: Session, email: str) -> BackfieldUser | None:
    users = users_by_normalized_email(session, email)
    if len(users) > 1:
        raise _conflict(f"Several users normalize to administrator email {email}")
    return users[0] if users else None


def _validate_existing_organization(
    session: Session,
    request: OrganizationProvisioningRequest,
    organization: BackfieldOrganization,
) -> OrganizationProvisioningReport:
    _require_resource_match(
        resource="organization",
        actual_name=str(organization.name),
        expected_name=request.organization.name,
    )
    organization_id = _required_id(organization, "organization")
    stylebook, workspace, project = _get_exact_starter_resources(
        session,
        request,
        organization,
    )
    emails = [request.client_admin_email]
    if request.support_admin_email is not None:
        emails.append(request.support_admin_email)
    admin_rows = session.exec(
        select(BackfieldUser)
        .join(
            BackfieldOrganizationMembership,
            BackfieldOrganizationMembership.user_id == BackfieldUser.id,
        )
        .where(
            BackfieldOrganizationMembership.organization_id == organization_id,
            BackfieldOrganizationMembership.role == ORG_ADMIN_ROLE,
        )
    ).all()
    actual_admin_emails = [normalize_user_email(str(user.email)) for user in admin_rows]
    expected_admin_emails = set(emails)
    if (
        len(actual_admin_emails) != len(set(actual_admin_emails))
        or set(actual_admin_emails) != expected_admin_emails
    ):
        raise _conflict(
            "Existing organization org_admin set does not match requested administrators"
        )
    users = tuple(
        _validate_existing_admin(
            session,
            organization_id=organization_id,
            email=email,
        )
        for email in emails
    )
    model_config_ids = _validate_existing_models(
        session,
        organization_id=organization_id,
        selected_ids=request.curated_model_ids,
    )
    return OrganizationProvisioningReport(
        organization_id=organization_id,
        organization_slug=request.organization.slug,
        organization_created=False,
        stylebook_id=_required_id(stylebook, "Stylebook"),
        stylebook_created=False,
        workspace_id=_required_id(workspace, "workspace"),
        workspace_created=False,
        project_id=_required_id(project, "project"),
        project_created=False,
        users=users,
        curated_model_ids=request.curated_model_ids,
        model_config_ids=model_config_ids,
    )


def _create_admin(
    session: Session,
    *,
    organization_id: int,
    email: str,
    password: SecretStr | None,
) -> ProvisionedUserReport:
    user = _find_user_by_normalized_email(session, email)
    created = False
    if user is None:
        if password is None:
            raise ValueError(f"A temporary password is required for new administrator {email}")
        plain_password = password.get_secret_value()
        validate_password_strength(plain_password, email=email)
        user = BackfieldUser(
            email=email,
            password_hash=hash_password(plain_password),
            must_change_password=True,
        )
        session.add(user)
        session.flush()
        created = True
    elif user.disabled_at is not None:
        raise _conflict(f"Existing administrator {email} is disabled")
    user_id = _required_id(user, "user")
    session.add(
        BackfieldOrganizationMembership(
            user_id=user_id,
            organization_id=organization_id,
            role=ORG_ADMIN_ROLE,
        )
    )
    session.flush()
    return ProvisionedUserReport(
        email=email,
        user_id=user_id,
        created=created,
        membership_created=True,
    )


def _create_organization(
    session: Session,
    request: OrganizationProvisioningRequest,
    passwords: TemporaryPasswordInput,
) -> OrganizationProvisioningReport:
    organization = BackfieldOrganization(
        name=request.organization.name,
        slug=request.organization.slug,
    )
    session.add(organization)
    session.flush()
    organization_id = _required_id(organization, "organization")

    stylebook = Stylebook(
        organization_id=organization_id,
        name=request.stylebook.name,
        slug=request.stylebook.slug,
        is_default=True,
    )
    session.add(stylebook)
    session.flush()
    stylebook_id = _required_id(stylebook, "Stylebook")

    workspace = BackfieldWorkspace(
        organization_id=organization_id,
        stylebook_id=stylebook_id,
        name=request.workspace.name,
        slug=request.workspace.slug,
    )
    session.add(workspace)
    session.flush()
    workspace_id = _required_id(workspace, "workspace")

    project = BackfieldProject(
        organization_id=organization_id,
        workspace_id=workspace_id,
        stylebook_id=stylebook_id,
        name=request.project.name,
        slug=request.project.slug,
    )
    session.add(project)
    session.flush()
    project_id = _required_id(project, "project")

    users = [
        _create_admin(
            session,
            organization_id=organization_id,
            email=request.client_admin_email,
            password=passwords.client_admin_password,
        )
    ]
    if request.support_admin_email is not None:
        users.append(
            _create_admin(
                session,
                organization_id=organization_id,
                email=request.support_admin_email,
                password=passwords.support_admin_password,
            )
        )

    model_config_ids: list[str] = []
    for model_id in request.curated_model_ids:
        template = CURATED_TEMPLATES[model_id]
        row = BackfieldAiModelConfig(
            organization_id=organization_id,
            name=template.label,
            provider=template.provider,
            provider_model_id=template.provider_model_id,
            model_kind=template.model_kind,
            status="active",
            capabilities_json=list(template.capabilities),
            currency="USD",
        )
        session.add(row)
        session.flush()
        model_config_ids.append(str(row.id))

    return OrganizationProvisioningReport(
        organization_id=organization_id,
        organization_slug=request.organization.slug,
        organization_created=True,
        stylebook_id=stylebook_id,
        stylebook_created=True,
        workspace_id=workspace_id,
        workspace_created=True,
        project_id=project_id,
        project_created=True,
        users=tuple(users),
        curated_model_ids=request.curated_model_ids,
        model_config_ids=tuple(model_config_ids),
    )


def provision_organization(
    session: Session,
    request: OrganizationProvisioningRequest,
    passwords: TemporaryPasswordInput,
) -> OrganizationProvisioningReport:
    """Create or verify starter rows within the caller-owned transaction.

    This function flushes as needed but never commits or rolls back. The caller owns the
    surrounding transaction and must roll it back after any exception.
    """
    organization = session.exec(
        select(BackfieldOrganization).where(
            BackfieldOrganization.slug == request.organization.slug
        )
    ).first()
    if organization is None:
        return _create_organization(session, request, passwords)
    return _validate_existing_organization(session, request, organization)


def run_organization_provisioning(
    request: OrganizationProvisioningRequest,
    passwords: TemporaryPasswordInput,
) -> OrganizationProvisioningReport:
    """Provision atomically through an isolated direct-database transaction."""
    engine = create_direct_engine()
    try:
        try:
            with Session(engine) as session, session.begin():
                return provision_organization(session, request, passwords)
        except IntegrityError:
            # A concurrent exact invocation may have committed the same organization first.
            with Session(engine) as winner_session, winner_session.begin():
                organization = winner_session.exec(
                    select(BackfieldOrganization).where(
                        BackfieldOrganization.slug == request.organization.slug
                    )
                ).first()
                if organization is None:
                    raise OrganizationProvisioningConflict(
                        "Provisioning conflicts with existing organization resources"
                    ) from None
                return _validate_existing_organization(
                    winner_session,
                    request,
                    organization,
                )
    finally:
        engine.dispose()
