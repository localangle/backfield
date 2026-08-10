from __future__ import annotations

from collections.abc import Generator
from typing import Any

from backfield_auth.gate import resolve_internal_auth
from backfield_db.session import get_engine
from fastapi import Cookie, Depends, Header
from sqlmodel import Session

from stylebook_api.webhook_dispatch import kick_webhook_dispatch_if_recorded


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
        # Runs after the route returns; events recorded but rolled back or
        # never committed were already cleared and produce no kick.
        kick_webhook_dispatch_if_recorded(session)


def get_auth(
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
    service_organization_id: int | None = Header(
        None,
        alias="X-Backfield-Organization-ID",
    ),
) -> dict[str, Any]:
    """Authenticate an internal browser session or trusted service."""
    auth = resolve_internal_auth(
        session,
        cookie=session_cookie,
        authorization=authorization,
        service_organization_id=service_organization_id,
    )
    session.info["backfield_auth"] = auth
    return auth
