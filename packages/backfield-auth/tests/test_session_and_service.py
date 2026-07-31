"""Unit tests for backfield-auth token helpers."""




def test_service_token_roundtrip(monkeypatch):
    monkeypatch.setenv("SERVICE_API_TOKEN", "secret-one")
    # Re-import to pick up env — package reads at import time; test module imports fresh
    import importlib

    import backfield_auth.service_tokens as st

    importlib.reload(st)
    assert st.verify_service_token("secret-one") is True
    assert st.verify_service_token("wrong") is False
    # Restore token set for integration tests that run later in the same pytest process.
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    importlib.reload(st)


def test_session_token_roundtrip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    import importlib

    import backfield_auth.session_tokens as s

    importlib.reload(s)
    s._session_serializer.cache_clear()
    tok = s.create_session_token(
        user_id=1,
        email="alice@example.com",
        projects=[10, 20],
        organization_id=1,
        org_role="member",
        is_admin=False,
    )
    data = s.verify_session_token(tok)
    assert data is not None
    assert data["username"] == "alice@example.com"
    assert data["user_id"] == 1
    assert data["projects"] == [10, 20]


def test_organization_selection_token_is_single_purpose_and_tamper_resistant(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-selection-secret")
    import importlib

    import backfield_auth.session_tokens as s

    importlib.reload(s)
    s._session_serializer.cache_clear()
    token = s.create_organization_selection_token(
        user_id=7,
        organization_ids=[3, 2, 3],
    )
    data = s.verify_organization_selection_token(token)
    assert data is not None
    assert data["user_id"] == 7
    assert data["organization_ids"] == [2, 3]
    assert s.verify_session_token(token) is None
    assert s.verify_organization_selection_token(token + "x") is None


def test_organization_selection_token_expires(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-expiry-secret")
    import importlib

    import backfield_auth.session_tokens as s

    importlib.reload(s)
    monkeypatch.setattr(s, "ORGANIZATION_SELECTION_MAX_AGE", -1)
    token = s.create_organization_selection_token(user_id=7, organization_ids=[2])
    assert s.verify_organization_selection_token(token) is None
