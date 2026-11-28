"""Fake OAuth: the refresh_token grant, its OAuth-format errors, and access checks (expiry, scopes) on the APIs."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_dataset import read_dataset_or_problems
from mock_oauth import (
    CALENDAR_EVENTS_READONLY_SCOPE,
    GMAIL_READONLY_SCOPE,
    MOCK_CLIENT_ID,
    MOCK_CLIENT_SECRET,
    MOCK_REFRESH_TOKEN,
)
from mock_settings import MockServerSettings
from mock_state import MockGoogleState

SETTINGS = MockServerSettings(environment="ci", log_level="INFO", dataset_name="synthetic_soltech")
VALID_GRANT = {
    "grant_type": "refresh_token",
    "client_id": MOCK_CLIENT_ID,
    "client_secret": MOCK_CLIENT_SECRET,
    "refresh_token": MOCK_REFRESH_TOKEN,
}
GMAIL_PROFILE = "/gmail/v1/users/me/profile"
CALENDAR_EVENTS = "/calendar/v3/calendars/primary/events"


class SettableClock:
    """A frozen clock a test can move forward, to expire tokens without waiting."""

    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    return SettableClock(dataset.seeded_at)


def make_client(clock, **state_options) -> tuple[TestClient, MockGoogleState]:
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    state = MockGoogleState(dataset, clock=clock, **state_options)
    return TestClient(build_mock_google_app(SETTINGS, state)), state


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_refresh_grant_issues_a_bearer_token_that_the_apis_accept(clock):
    client, _ = make_client(clock)

    response = client.post("/token", data=VALID_GRANT)

    body = response.json()
    assert response.status_code == 200 and body["token_type"] == "Bearer"
    assert body["access_token"].startswith("ya29.mock-") and body["expires_in"] == 3600
    assert set(body["scope"].split()) == {GMAIL_READONLY_SCOPE, CALENDAR_EVENTS_READONLY_SCOPE}
    assert client.get(GMAIL_PROFILE, headers=bearer(body["access_token"])).status_code == 200


@pytest.mark.parametrize(
    ("change", "status", "error"),
    [
        ({"grant_type": "authorization_code"}, 400, "unsupported_grant_type"),
        ({"client_secret": "wrong"}, 401, "invalid_client"),
        ({"refresh_token": "wrong"}, 400, "invalid_grant"),
        ({"scope": "https://www.googleapis.com/auth/calendar.readonly"}, 400, "invalid_scope"),
    ],
)
def test_token_endpoint_errors_use_oauths_own_format(clock, change, status, error):
    client, _ = make_client(clock)

    response = client.post("/token", data={**VALID_GRANT, **change})

    assert response.status_code == status
    assert response.json()["error"] == error and "error_description" in response.json()


def test_a_revoked_refresh_token_is_invalid_grant(clock):
    client, state = make_client(clock)
    state.oauth.refresh_token_revoked = True

    response = client.post("/token", data=VALID_GRANT)

    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_requesting_a_subset_of_scopes_gets_a_token_with_just_those(clock):
    client, _ = make_client(clock)

    token = client.post("/token", data={**VALID_GRANT, "scope": GMAIL_READONLY_SCOPE}).json()["access_token"]

    assert client.get(GMAIL_PROFILE, headers=bearer(token)).status_code == 200
    calendar = client.get(CALENDAR_EVENTS, params={"singleEvents": "true"}, headers=bearer(token))
    assert calendar.status_code == 403


def test_unknown_and_expired_tokens_are_401_so_clients_refresh(clock):
    client, _ = make_client(clock, access_token_ttl_seconds=60)
    token = client.post("/token", data=VALID_GRANT).json()["access_token"]

    assert client.get(GMAIL_PROFILE, headers=bearer("ya29.made-up")).status_code == 401
    clock.now += timedelta(seconds=61)
    expired = client.get(GMAIL_PROFILE, headers=bearer(token))
    assert expired.status_code == 401 and expired.json()["error"]["errors"][0]["reason"] == "authError"


def test_gmail_only_consent_is_refused_on_calendar_with_insufficient_permissions(clock):
    # A mailbox authorized for Gmail and never re-consented for Calendar (the calendar contract's re-consent step).
    client, _ = make_client(clock, granted_scopes=(GMAIL_READONLY_SCOPE,))
    token = client.post("/token", data=VALID_GRANT).json()["access_token"]

    calendar = client.get(CALENDAR_EVENTS, params={"singleEvents": "true"}, headers=bearer(token))

    assert client.get(GMAIL_PROFILE, headers=bearer(token)).status_code == 200
    assert calendar.status_code == 403
    assert calendar.json()["error"]["errors"][0]["reason"] == "insufficientPermissions"


def test_reset_forgets_issued_tokens_and_revocation(clock):
    client, state = make_client(clock)
    token = client.post("/token", data=VALID_GRANT).json()["access_token"]
    state.oauth.refresh_token_revoked = True

    state.reset()

    assert client.get(GMAIL_PROFILE, headers=bearer(token)).status_code == 401
    assert client.post("/token", data=VALID_GRANT).status_code == 200
