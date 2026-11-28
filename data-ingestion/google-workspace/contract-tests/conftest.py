"""Fixtures for the contract tests: the real master code against the running mock Google server and a real Postgres.

These are integration tests, kept apart from both services' unit tests on purpose: they need the network (the mock
container) and a database. Each fixture skips cleanly when its dependency is not configured:

- GOOGLE_WORKSPACE_MOCK_URL: base URL of the mock (e.g. http://google-workspace-mock:8090 in Compose).
- SOLNEXUS_TEST_DATABASE_URL: a throwaway "*_ingest_test" database migrated to head (data-platform/README.md#tests).

The master's code is imported from google-workspace-master-service (put on PYTHONPATH by the Compose service and CI),
exactly as it runs in production: real google-auth, real requests, real SQL.
"""

from __future__ import annotations

import json
import os
import uuid

import psycopg2
import pytest
import requests

# The fixed, public, fake credentials of the mock's OAuth server (mock_oauth.py). They unlock only the mock.
MOCK_CLIENT_ID = "solnexus-mock-client.apps.example.test"
MOCK_CLIENT_SECRET = "mock-client-secret-not-a-real-secret"
MOCK_REFRESH_TOKEN = "mock-refresh-token-not-a-real-secret"
# The mailbox the mock's synthetic_soltech dataset serves.
MOCK_MAILBOX = "sales@soltech.example.test"
INGEST_TEST_DB_SUFFIX = "_ingest_test"


@pytest.fixture(scope="session")
def mock_url() -> str:
    url = os.environ.get("GOOGLE_WORKSPACE_MOCK_URL", "").rstrip("/")
    if not url:
        pytest.skip("GOOGLE_WORKSPACE_MOCK_URL not set; skipping contract tests against the mock")
    return url


@pytest.fixture(autouse=True)
def reset_mock(mock_url) -> None:
    """Every test starts from the dataset seed with no faults, tokens or revocation left over from the last one.

    Autouse and dependent on mock_url, so every contract test needs the mock and is skipped without it.
    """
    response = requests.post(f"{mock_url}/_mock/reset", timeout=10)
    response.raise_for_status()


@pytest.fixture
def mock_control(mock_url):
    """POST to a /_mock control route and return its data; any failure fails the test loudly."""

    def post(path: str, body: dict | None = None) -> dict:
        response = requests.post(f"{mock_url}/_mock/{path}", json=body, timeout=10)
        assert response.status_code in (200, 201), response.text
        return response.json()["data"]

    return post


@pytest.fixture
def token_file(tmp_path) -> str:
    """An authorized-user token file in the exact shape the SNX-21 consent flow writes for production.

    It has no token_uri on purpose: google-auth ignores one in the file anyway (a tampered file must not redirect
    the secret). Where tokens are refreshed is configuration, passed to the client as token_uri (below).
    """
    path = tmp_path / "gmail-token.json"
    path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": MOCK_CLIENT_ID,
                "client_secret": MOCK_CLIENT_SECRET,
                "refresh_token": MOCK_REFRESH_TOKEN,
            }
        )
    )
    return str(path)


@pytest.fixture
def mock_token_uri(mock_url) -> str:
    """The token address the master is configured with during these tests: the mock's /token, not Google's."""
    return f"{mock_url}/token"


@pytest.fixture
def db():
    """A connection to the throwaway ingest test database, with this mailbox's Gmail cursor cleared.

    Bronze is append-only, so rows from earlier runs stay; the tests therefore assert on what a sync did
    (inserted + already stored) rather than on absolute row counts. The checkpoint row is not append-only, and
    clearing it makes every test start with "no cursor yet", i.e. a full sync.
    """
    url = os.environ.get("SOLNEXUS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SOLNEXUS_TEST_DATABASE_URL not set; skipping Postgres-backed contract test")
    conn = psycopg2.connect(url)
    if not conn.info.dbname.endswith(INGEST_TEST_DB_SUFFIX):
        conn.close()
        pytest.fail(f"refusing to write test rows outside a '*{INGEST_TEST_DB_SUFFIX}' database")
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM app.ingestion_checkpoints WHERE source_channel = 'gmail' AND source_account_id = %s",
            (MOCK_MAILBOX,),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def job_run_id() -> str:
    return f"contract-test-{uuid.uuid4().hex[:12]}"
