from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


@lru_cache
def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache
def create_api_engine(database_url: str, statement_timeout_ms: int) -> Engine:
    """The API's engine: Postgres cancels any statement running past the timeout.

    Separate from `create_database_engine` on purpose, which the worker shares: its batch
    jobs legitimately run longer than a request may. Zero means no timeout.
    """
    if statement_timeout_ms <= 0:
        return create_database_engine(database_url)
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"options": f"-c statement_timeout={statement_timeout_ms}"},
    )


def open_session(database_url: str, *, statement_timeout_ms: int = 0) -> Iterator[Session]:
    with Session(create_api_engine(database_url, statement_timeout_ms)) as session:
        yield session
