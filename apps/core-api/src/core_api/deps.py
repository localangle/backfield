"""FastAPI dependencies for Core API."""

from __future__ import annotations

from collections.abc import Generator

from backfield_db.session import get_engine
from fastapi import Cookie, Depends, Header
from sqlmodel import Session

from core_api.authz import resolve_auth


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def get_auth(
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    return resolve_auth(session, cookie=session_cookie, authorization=authorization)
