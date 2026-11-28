"""Unit tests for the shared Google API layer: retries, backoff and error classification, over a fake session."""

from __future__ import annotations

import pytest
import requests
from google.auth.exceptions import RefreshError

from services.google_api import (
    GoogleApi,
    GoogleAuthError,
    GoogleNotFound,
    GooglePolicyError,
    GoogleQuotaExhausted,
    GoogleRetriesExhausted,
    RetryPolicy,
)


ROOT = "https://api.example.test/v1"


def response(status: int, body: dict | None = None, headers: dict | None = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = requests.compat.json.dumps(body or {}).encode()
    resp.headers.update(headers or {})
    return resp


def error(status: int, reason: str, headers: dict | None = None) -> requests.Response:
    return response(status, {"error": {"code": status, "errors": [{"reason": reason}]}}, headers)


class FakeSession:
    """Returns (or raises) the queued outcomes in order and records each requested path."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.paths: list[str] = []

    def get(self, url, params=None, timeout=None):
        assert timeout is not None, "every call must set a timeout"
        self.paths.append(url.removeprefix(ROOT))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(*outcomes, max_retries: int = 5):
    sleeps: list[float] = []
    session = FakeSession(*outcomes)
    api = GoogleApi(session, ROOT, "Gmail", RetryPolicy(max_retries=max_retries), sleep=sleeps.append)
    return api, session, sleeps


@pytest.mark.parametrize(
    "failure",
    [error(429, "rateLimitExceeded"), error(403, "userRateLimitExceeded"), error(503, "backendError"),
     requests.ConnectionError("reset")],
)


def test_transient_failures_are_retried_then_succeed(failure):
    api, session, sleeps = client(failure, response(200, {"emailAddress": "x", "historyId": "1"}))

    assert api.get("/profile")["historyId"] == "1"
    assert len(session.paths) == 2
    assert len(sleeps) == 1


def test_retries_are_bounded():
    api, session, sleeps = client(*[error(503, "backendError")] * 3, max_retries=2)

    with pytest.raises(GoogleRetriesExhausted):
        api.get("/profile")
    assert len(session.paths) == 3  # first try + 2 retries
    assert len(sleeps) == 2


def test_server_retry_after_is_respected():
    api, _, sleeps = client(error(429, "rateLimitExceeded", {"Retry-After": "40"}), response(200, {}))

    api.get("/profile")

    assert sleeps[0] >= 40


def test_backoff_grows_and_is_capped():
    policy = RetryPolicy(base_delay=1, max_delay=32)

    delays = [policy.delay(n) for n in range(8)]

    assert 1 <= delays[0] < 2
    assert 4 <= delays[2] < 5
    assert all(d < 33 for d in delays)  # 32s cap + at most 1s jitter


@pytest.mark.parametrize("failure", [error(403, "domainPolicy"), error(400, "invalidArgument")])


def test_policy_and_request_errors_fail_fast(failure):
    api, session, sleeps = client(failure)

    with pytest.raises(GooglePolicyError, match="domainPolicy|invalidArgument"):
        api.get("/profile")
    assert sleeps == []


def test_temporary_token_endpoint_failure_is_retried():
    api, _, sleeps = client(RefreshError("token endpoint 503", retryable=True), response(200, {"historyId": "1"}))

    assert api.get("/profile")["historyId"] == "1"
    assert len(sleeps) == 1


@pytest.mark.parametrize("reason", ["dailyLimitExceeded", "quotaExceeded"])


def test_used_up_daily_quota_is_not_an_operator_problem_or_a_quick_retry(reason):
    api, _, sleeps = client(error(403, reason))

    with pytest.raises(GoogleQuotaExhausted):
        api.get("/profile")
    assert sleeps == []  # waiting seconds will not refill a daily quota


@pytest.mark.parametrize("failure", [RefreshError("invalid_grant"), error(401, "authError")])


def test_expired_or_revoked_consent_needs_reauthorization(failure):
    api, _, sleeps = client(failure)

    with pytest.raises(GoogleAuthError):
        api.get("/profile")
    assert sleeps == []


def test_error_messages_do_not_echo_response_bodies():
    leaked = response(400, {"error": {"errors": [{"reason": "badRequest"}], "message": "lead@clinic.example.test"}})
    api, _, _ = client(leaked)

    with pytest.raises(GooglePolicyError) as exc_info:
        api.get("/profile")
    assert "example.test" not in str(exc_info.value)


def test_not_found_is_left_for_the_product_client_to_interpret():
    api, _, sleeps = client(error(404, "notFound"))

    with pytest.raises(GoogleNotFound):
        api.get("/messages/gone")
    assert sleeps == []


def test_errors_name_the_product():
    api, _, _ = client(error(403, "domainPolicy"))

    with pytest.raises(GooglePolicyError, match="^Gmail refused"):
        api.get("/profile")
