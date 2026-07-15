"""Helpers for Core API tests after HTTP bootstrap removal."""

from __future__ import annotations

from core_api.bootstrap_users import ensure_first_org_admin
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session


def attach_test_engine(client: TestClient, engine: Engine) -> TestClient:
    """Stash the SQLite engine on the client for seed helpers."""
    client.test_engine = engine  # type: ignore[attr-defined]
    return client


def _client_engine(client: TestClient) -> Engine:
    engine = getattr(client, "test_engine", None)
    if engine is None:
        raise RuntimeError(
            "TestClient is missing test_engine; "
            "call attach_test_engine(client, engine) in the fixture"
        )
    return engine


def seed_first_admin(
    client: TestClient,
    email: str,
    password: str,
    display_name: str | None = None,
) -> dict[str, str | int | bool]:
    """Create the first org admin through the shared DB helper (not HTTP)."""
    with Session(_client_engine(client)) as session:
        result = ensure_first_org_admin(session, email, password, display_name)
    if result is None:
        raise RuntimeError(f"Could not create first admin for {email}; users already exist")
    return result


def seed_and_login(
    client: TestClient,
    email: str,
    password: str,
    display_name: str | None = None,
) -> None:
    seed_first_admin(client, email, password, display_name)
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    if login.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {login.status_code} {login.text}")
