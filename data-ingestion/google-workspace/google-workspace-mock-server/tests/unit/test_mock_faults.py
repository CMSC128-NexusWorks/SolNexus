"""Injected faults and delays: scheduled failures answer exactly as Google does, then requests succeed again."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_dataset import read_dataset_or_problems
from mock_faults import FaultPlan, ScheduledFault
from mock_oauth import MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_REFRESH_TOKEN
from mock_settings import MockServerSettings
from mock_state import MockGoogleState

SETTINGS = MockServerSettings(environment="ci", log_level="INFO", dataset_name="synthetic_soltech")
GMAIL_PROFILE = "/gmail/v1/users/me/profile"
CALENDAR_EVENTS = "/calendar/v3/calendars/primary/events"
VALID_GRANT = {
    "grant_type": "refresh_token",
    "client_id": MOCK_CLIENT_ID,
    "client_secret": MOCK_CLIENT_SECRET,
    "refresh_token": MOCK_REFRESH_TOKEN,
}


@pytest.fixture
def state() -> MockGoogleState:
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    return MockGoogleState(dataset, clock=lambda: dataset.seeded_at)


@pytest.fixture
def client(state) -> TestClient:
    token = state.oauth.issue_access_token(state.oauth.granted_scopes, state.clock()).token
    return TestClient(build_mock_google_app(SETTINGS, state), headers={"Authorization": f"Bearer {token}"})


def reason_of(response) -> str:
    return response.json()["error"]["errors"][0]["reason"]


def test_a_scheduled_rate_limit_fails_that_many_calls_then_clears(client, state):
    state.faults.schedule(ScheduledFault("gmail", "rate_limit", remaining=2, retry_after_seconds=7))

    statuses = [client.get(GMAIL_PROFILE).status_code for _ in range(3)]

    assert statuses == [429, 429, 200]
    assert state.faults.scheduled == []


def test_rate_limit_carries_retry_after_and_googles_reason(client, state):
    state.faults.schedule(ScheduledFault("gmail", "rate_limit", remaining=1, retry_after_seconds=7))

    response = client.get(GMAIL_PROFILE)

    assert response.headers["Retry-After"] == "7" and reason_of(response) == "rateLimitExceeded"


@pytest.mark.parametrize(
    ("kind", "status", "reason"),
    [
        ("user_rate_limit", 403, "userRateLimitExceeded"),
        ("daily_quota", 403, "dailyLimitExceeded"),
        ("backend_error", 500, "backendError"),
        ("service_unavailable", 503, "backendError"),
        ("expired_access_token", 401, "authError"),
    ],
)
def test_each_api_fault_answers_like_google(client, state, kind, status, reason):
    state.faults.schedule(ScheduledFault("calendar", kind, remaining=1))

    response = client.get(CALENDAR_EVENTS, params={"singleEvents": "true"})

    assert response.status_code == status and reason_of(response) == reason


def test_faults_only_hit_their_own_target(client, state):
    state.faults.schedule(ScheduledFault("calendar", "backend_error", remaining=1))

    assert client.get(GMAIL_PROFILE).status_code == 200
    assert client.get(CALENDAR_EVENTS, params={"singleEvents": "true"}).status_code == 500


def test_faults_are_consumed_in_the_order_they_were_scheduled(client, state):
    state.faults.schedule(ScheduledFault("gmail", "rate_limit", remaining=1))
    state.faults.schedule(ScheduledFault("gmail", "backend_error", remaining=1))

    assert [client.get(GMAIL_PROFILE).status_code for _ in range(3)] == [429, 500, 200]


@pytest.mark.parametrize(
    ("kind", "status", "error"),
    [("invalid_grant", 400, "invalid_grant"), ("token_server_error", 500, "internal_failure")],
)
def test_token_endpoint_faults_use_oauths_format(client, state, kind, status, error):
    state.faults.schedule(ScheduledFault("token", kind, remaining=1))

    failed = client.post("/token", data=VALID_GRANT)
    recovered = client.post("/token", data=VALID_GRANT)

    assert failed.status_code == status and failed.json()["error"] == error
    assert recovered.status_code == 200


def test_mismatched_fault_and_target_is_refused():
    plan = FaultPlan()

    with pytest.raises(ValueError):
        plan.schedule(ScheduledFault("token", "rate_limit", remaining=1))
    with pytest.raises(ValueError):
        plan.schedule(ScheduledFault("gmail", "invalid_grant", remaining=1))
    with pytest.raises(ValueError):
        plan.schedule(ScheduledFault("gmail", "rate_limit", remaining=0))


def test_configured_delay_slows_only_its_target(client, state):
    state.faults.delay_ms_by_target["calendar"] = 150

    started = time.monotonic()
    client.get(GMAIL_PROFILE)
    gmail_seconds = time.monotonic() - started
    started = time.monotonic()
    client.get(CALENDAR_EVENTS, params={"singleEvents": "true"})
    calendar_seconds = time.monotonic() - started

    assert calendar_seconds >= 0.15 and gmail_seconds < 0.15


def test_default_delay_comes_from_startup_settings():
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    state = MockGoogleState(dataset, default_response_delay_ms=40)

    assert state.faults.delay_seconds_for("gmail") == pytest.approx(0.04)


def test_reset_clears_scheduled_faults_and_delays(state):
    state.faults.schedule(ScheduledFault("gmail", "rate_limit", remaining=5))
    state.faults.delay_ms_by_target["gmail"] = 500

    state.reset()

    assert state.faults.scheduled == [] and state.faults.delay_seconds_for("gmail") == 0


def test_retry_after_is_sent_with_the_403_rate_limit_too(client, state):
    # Regression: the header used to be added only to 429s, though the master retries 403 userRateLimitExceeded as
    # throttling too and honours Retry-After on it.
    state.faults.schedule(ScheduledFault("gmail", "user_rate_limit", remaining=1, retry_after_seconds=40))

    response = client.get(GMAIL_PROFILE)

    assert response.status_code == 403 and response.headers["Retry-After"] == "40"


def test_retry_after_on_a_non_throttling_fault_is_refused_not_dropped():
    plan = FaultPlan()

    with pytest.raises(ValueError, match="retry_after_seconds applies only to"):
        plan.schedule(ScheduledFault("gmail", "backend_error", remaining=1, retry_after_seconds=5))
