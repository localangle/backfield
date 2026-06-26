"""Production-safe, idempotent initial organization and admin seeding."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass

from sqlmodel import Session, select

from backfield_db.models import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldUser,
    Stylebook,
)
from backfield_db.passwords import hash_password
from backfield_db.session import get_engine

logger = logging.getLogger(__name__)

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Backfield"
DEFAULT_STYLEBOOK_NAME = "Default Stylebook"
ORG_ADMIN_ROLE = "org_admin"


@dataclass(frozen=True)
class SeedReport:
    organization_id: int
    organization_slug: str
    organization_created: bool
    admin_user_id: int | None
    admin_email: str
    admin_created: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def ensure_initial_org_and_admin(
    session: Session,
    *,
    org_slug: str,
    org_name: str,
    admin_email: str,
    admin_password: str,
    admin_display_name: str | None = None,
) -> SeedReport:
    """Ensure org (by slug) and admin user (by email) exist without mutating existing rows."""
    slug = org_slug.strip()
    name = org_name.strip()
    email = admin_email.strip().lower()
    password = admin_password
    if not slug:
        raise ValueError("org_slug is required")
    if not name:
        raise ValueError("org_name is required")
    if not email:
        raise ValueError("admin_email is required")
    if not password:
        raise ValueError("admin_password is required")

    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == slug)
    ).first()
    organization_created = False
    if org is None:
        org = BackfieldOrganization(name=name, slug=slug)
        session.add(org)
        session.flush()
        organization_created = True
    elif org.id is None:
        raise RuntimeError("organization row missing id after flush")

    organization_id = int(org.id)
    user = session.exec(select(BackfieldUser).where(BackfieldUser.email == email)).first()
    admin_created = False
    admin_user_id: int | None = None
    if user is None:
        user = BackfieldUser(
            email=email,
            password_hash=hash_password(password),
            display_name=admin_display_name.strip() if admin_display_name else None,
        )
        session.add(user)
        session.flush()
        if user.id is None:
            raise RuntimeError("user row missing id after flush")
        admin_user_id = int(user.id)
        session.add(
            BackfieldOrganizationMembership(
                user_id=admin_user_id,
                organization_id=organization_id,
                role=ORG_ADMIN_ROLE,
            )
        )
        admin_created = True
    else:
        admin_user_id = int(user.id) if user.id is not None else None

    session.commit()
    return SeedReport(
        organization_id=organization_id,
        organization_slug=slug,
        organization_created=organization_created,
        admin_user_id=admin_user_id,
        admin_email=email,
        admin_created=admin_created,
    )


def apply_init_display_names(
    session: Session,
    *,
    organization_id: int,
    org_name: str,
    stylebook_name: str,
) -> None:
    """Apply init-chosen display names when rows still use migration defaults."""
    desired_org_name = org_name.strip()
    desired_stylebook_name = stylebook_name.strip()

    org = session.get(BackfieldOrganization, organization_id)
    if (
        org is not None
        and desired_org_name
        and org.name == DEFAULT_ORG_NAME
        and desired_org_name != org.name
    ):
        org.name = desired_org_name
        session.add(org)

    stylebook = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == organization_id,
            Stylebook.is_default == True,  # noqa: E712
        )
    ).first()
    if stylebook is None:
        stylebook = session.exec(
            select(Stylebook).where(
                Stylebook.organization_id == organization_id,
                Stylebook.slug == "default",
            )
        ).first()
    if stylebook is None:
        stylebook = Stylebook(
            organization_id=organization_id,
            slug="default",
            name=desired_stylebook_name or DEFAULT_STYLEBOOK_NAME,
            is_default=True,
        )
        session.add(stylebook)
    elif (
        desired_stylebook_name
        and stylebook.name == DEFAULT_STYLEBOOK_NAME
        and desired_stylebook_name != stylebook.name
    ):
        stylebook.name = desired_stylebook_name
        session.add(stylebook)

    session.commit()


def run_init_seed(
    *,
    org_slug: str = DEFAULT_ORG_SLUG,
    org_name: str = DEFAULT_ORG_NAME,
    stylebook_name: str = DEFAULT_STYLEBOOK_NAME,
    admin_email: str,
    admin_password: str,
    admin_display_name: str | None = None,
) -> SeedReport:
    with Session(get_engine()) as session:
        report = ensure_initial_org_and_admin(
            session,
            org_slug=org_slug,
            org_name=org_name,
            admin_email=admin_email,
            admin_password=admin_password,
            admin_display_name=admin_display_name,
        )
        apply_init_display_names(
            session,
            organization_id=report.organization_id,
            org_name=org_name,
            stylebook_name=stylebook_name,
        )
        return report


def run_seed(
    *,
    org_slug: str = DEFAULT_ORG_SLUG,
    org_name: str = DEFAULT_ORG_NAME,
    admin_email: str,
    admin_password: str,
    admin_display_name: str | None = None,
) -> SeedReport:
    with Session(get_engine()) as session:
        return ensure_initial_org_and_admin(
            session,
            org_slug=org_slug,
            org_name=org_name,
            admin_email=admin_email,
            admin_password=admin_password,
            admin_display_name=admin_display_name,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.error("Use `backfield seed` instead of invoking backfield_db.seed.main directly")
    return 1


if __name__ == "__main__":
    sys.exit(main())
