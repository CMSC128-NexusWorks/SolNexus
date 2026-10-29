from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db import sqlalchemy_url

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def run_migrations_offline() -> None:
    """Render SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=sqlalchemy_url(settings.database_url),
        literal_binds=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url(settings.database_url), poolclass=pool.NullPool)
    with engine.connect() as connection:
        # One transaction per revision: a failed revision rolls back alone and earlier ones stay applied.
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
