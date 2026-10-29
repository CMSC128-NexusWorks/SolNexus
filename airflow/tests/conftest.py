"""Shared fixtures. Postgres-backed tests run only when SOLNEXUS_TEST_DATABASE_URL is set.

That URL must point at a throwaway database migrated to head (see airflow/README.md), never the dev
database: bronze is append-only, so test rows could not be cleaned up.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import psycopg2
import pytest

STAFF_USER_ID = "00000000-0000-4000-8000-0000000000aa"


@pytest.fixture
def db():
    url = os.environ.get("SOLNEXUS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SOLNEXUS_TEST_DATABASE_URL not set; skipping Postgres-backed test")
    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        # Mappings require a confirming staff user.
        cur.execute(
            "INSERT INTO app.staff_users (user_id, email, password_hash) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (STAFF_USER_ID, "tests@example.test", "$test$login-disabled"),
        )
    conn.commit()
    yield conn
    conn.close()


@dataclass(frozen=True)
class Parties:
    mailbox: str
    lead: str


@pytest.fixture
def parties() -> Parties:
    """Addresses unique to one test, so tests never see each other's rows in the shared test database."""
    tag = uuid.uuid4().hex[:10]
    return Parties(mailbox=f"sales-{tag}@soltech.example.test", lead=f"lead-{tag}@clinic.example.test")
