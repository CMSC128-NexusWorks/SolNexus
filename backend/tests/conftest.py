"""Shared fixtures. Tests run against a separate `<database>_test` database migrated to head,
so the dev database and its seed data are never touched."""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Point the app at the test database before any app module reads settings.
_dev_url = make_url(os.environ["DATABASE_URL"])
_test_url = _dev_url.set(database=f"{_dev_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.staff import set_staff_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

STAFF_EMAIL = "staff.one@example.test"
STAFF_PASSWORD = "correct horse battery staple"


def _create_test_database() -> None:
    admin = create_engine(
        _dev_url.set(drivername="postgresql+psycopg", database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _test_url.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _create_test_database()
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean_staff_tables():
    # DELETE, not TRUNCATE ... CASCADE: a cascade would reach append-only tables whose triggers reject it.
    with engine.begin() as conn:
        # Import tests leave clinics, ledger rows and append-only status events behind. Candidate lookup
        # compares new rows with every existing clinic, so leftovers would turn the next test's rows into
        # needs_review. replica mode skips user triggers (the append-only guards) and foreign-key checks
        # for this transaction only; the test database role is a superuser, as the setting requires.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for table in (
            "clinic_status_events", "clinic_field_events", "import_field_review_candidates",
            "import_field_reviews", "import_rows", "import_row_decisions", "import_batches", "clinics",
        ):
            conn.execute(text(f"DELETE FROM app.{table}"))
        conn.execute(text("DELETE FROM app.staff_sessions"))
        conn.execute(text("DELETE FROM app.staff_users"))


@pytest.fixture
def run_sql():
    """Run one statement in its own committed transaction, as an operator or a later request would."""

    def run(statement: str, **params):
        with engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return result.all() if result.returns_rows else None

    return run


@pytest.fixture
def client():
    # https base URL: the session cookie is Secure, so the client only sends it over https.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def staff():
    with engine.begin() as conn:
        user_id = set_staff_password(conn, STAFF_EMAIL, STAFF_PASSWORD)
    return {"user_id": str(user_id), "email": STAFF_EMAIL, "password": STAFF_PASSWORD}


@pytest.fixture
def signed_in(client, staff):
    response = client.post("/api/v1/auth/login", json={"email": staff["email"], "password": staff["password"]})
    assert response.status_code == 200
    return client
