"""Required password changes gate sessions without affecting bearer authentication."""

from __future__ import annotations

from backfield_auth import gate
from sqlalchemy import create_engine
from sqlmodel import Session


def test_project_api_key_auth_is_unaffected_by_password_change_gate(monkeypatch) -> None:
    expected = {"type": "api_key", "project_id": 42}
    monkeypatch.setattr(gate, "verify_service_token", lambda _token: False)
    monkeypatch.setattr(
        gate,
        "try_resolve_bearer_api_key",
        lambda _session, _token: expected,
    )
    with Session(create_engine("sqlite://")) as session:
        assert (
            gate.resolve_auth(
                session,
                cookie="a-flagged-session-cookie",
                authorization="Bearer bfk_example",
            )
            == expected
        )


def test_service_auth_is_unaffected_by_password_change_gate(monkeypatch) -> None:
    monkeypatch.setattr(gate, "verify_service_token", lambda _token: True)
    with Session(create_engine("sqlite://")) as session:
        auth = gate.resolve_auth(
            session,
            cookie="a-flagged-session-cookie",
            authorization="Bearer service-token",
            service_organization_id=7,
        )
    assert auth == {
        "type": "service",
        "is_admin": True,
        "organization_id": 7,
    }
