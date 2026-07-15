"""SESSION_SECRET must be configured explicitly at use time."""

from __future__ import annotations

import importlib

import pytest


def test_missing_session_secret_raises_at_use_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import backfield_auth.session_tokens as session_tokens

    importlib.reload(session_tokens)
    session_tokens._session_serializer.cache_clear()

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        session_tokens.require_session_secret()

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        session_tokens.create_session_token(
            user_id=1,
            email="a@example.com",
            projects=[1],
            organization_id=1,
            org_role="member",
        )

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret")
    session_tokens._session_serializer.cache_clear()
    token = session_tokens.create_session_token(
        user_id=1,
        email="a@example.com",
        projects=[1],
        organization_id=1,
        org_role="member",
    )
    assert session_tokens.verify_session_token(token) is not None


def test_dev_secret_key_is_not_an_implicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import backfield_auth.session_tokens as session_tokens

    importlib.reload(session_tokens)
    session_tokens._session_serializer.cache_clear()

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        session_tokens.require_session_secret()

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret")
    session_tokens._session_serializer.cache_clear()
    assert session_tokens.require_session_secret() == "dev-session-secret"
