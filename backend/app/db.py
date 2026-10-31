from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, create_engine

from app.core.config import settings


def sqlalchemy_url(database_url: str) -> str:
    # .env uses the libpq form shared with other tools; SQLAlchemy needs the psycopg 3 driver named.
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


# Queries are hand-written SQL through SQLAlchemy Core (`text()`), matching the hand-written migrations.
# hide_parameters keeps bound values (passwords' hashes, emails, imported lead rows) out of exception
# messages and therefore out of any log or traceback that prints them.
engine = create_engine(sqlalchemy_url(settings.database_url), pool_pre_ping=True, hide_parameters=True)


def get_db() -> Iterator[Connection]:
    """FastAPI dependency: one transaction per request, committed on success and rolled back on error."""
    with engine.begin() as conn:
        yield conn


# Routes and dependencies take `conn: Db`, never a bare Depends(get_db). scope="function" commits when
# the route returns, before the response is sent. The default ("request") commits after the client
# already has the response, so a login could hand out a cookie for a session row that never committed,
# and a request sent right after it could arrive before the commit and get a 401.
Db = Annotated[Connection, Depends(get_db, scope="function")]
