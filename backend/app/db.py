from collections.abc import Iterator

from sqlalchemy import Connection, create_engine

from app.core.config import settings


def sqlalchemy_url(database_url: str) -> str:
    # .env uses the libpq form shared with other tools; SQLAlchemy needs the psycopg 3 driver named.
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


# Queries are hand-written SQL through SQLAlchemy Core (`text()`), matching the hand-written migrations.
engine = create_engine(sqlalchemy_url(settings.database_url), pool_pre_ping=True)


def get_db() -> Iterator[Connection]:
    """FastAPI dependency: one transaction per request, committed on success and rolled back on error."""
    with engine.begin() as conn:
        yield conn
