from __future__ import annotations

from collections.abc import Generator
from typing import Any

from backfield_auth.gate import resolve_auth
from backfield_db.session import get_engine
from fastapi import Cookie, Depends, Header
from sqlmodel import Session


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def get_auth(
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Session cookie, service Bearer, or project API key (`bfk_`)."""
    return resolve_auth(session, cookie=session_cookie, authorization=authorization)
