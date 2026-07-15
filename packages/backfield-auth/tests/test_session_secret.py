"""SESSION_SECRET must be configured explicitly."""

from __future__ import annotations

import importlib

import pytest


def test_missing_session_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import backfield_auth.session_tokens as session_tokens

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        importlib.reload(session_tokens)

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret")
    importlib.reload(session_tokens)


def test_dev_secret_key_is_not_an_implicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import backfield_auth.session_tokens as session_tokens

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        importlib.reload(session_tokens)

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret")
    importlib.reload(session_tokens)
