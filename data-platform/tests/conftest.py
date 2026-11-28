"""Shared fixtures. Postgres-backed tests run only when SOLNEXUS_TEST_DATABASE_URL is set.

That URL must point at a throwaway database migrated to head (see data-platform/README.md). It must not be the
dev database or the backend suite's "<db>_test" database. The Google Workspace master's tests share this
database and leave append-only rows (bronze messages, staff-confirmed mappings) that can never be deleted,
so the fixture accepts only databases named "*_ingest_test".
"""

from __future__ import annotations

import os

import psycopg2
import pytest

INGEST_TEST_DB_SUFFIX = "_ingest_test"


@pytest.fixture
def db():
    url = os.environ.get("SOLNEXUS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SOLNEXUS_TEST_DATABASE_URL not set; skipping Postgres-backed test")
    conn = psycopg2.connect(url)
    if not conn.info.dbname.endswith(INGEST_TEST_DB_SUFFIX):
        conn.close()
        pytest.fail(f"refusing to write test rows outside a '*{INGEST_TEST_DB_SUFFIX}' database")
    yield conn
    conn.close()

