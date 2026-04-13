from collections.abc import Generator

from backfield_db.session import get_engine
from sqlmodel import Session


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
