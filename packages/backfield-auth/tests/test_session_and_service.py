"""Unit tests for backfield-auth token helpers."""




def test_service_token_roundtrip(monkeypatch):
    monkeypatch.setenv("SERVICE_API_TOKEN", "secret-one")
    # Re-import to pick up env — package reads at import time; test module imports fresh
    import importlib

    import backfield_auth.service_tokens as st

    importlib.reload(st)
    assert st.verify_service_token("secret-one") is True
    assert st.verify_service_token("wrong") is False


def test_session_token_roundtrip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    import importlib

    import backfield_auth.session_tokens as s

    importlib.reload(s)
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
