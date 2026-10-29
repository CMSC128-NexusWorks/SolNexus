"""Unit tests for the Gmail client's retry and error classification, using a fake HTTP session."""

from __future__ import annotations

import pytest
import requests
from google.auth.exceptions import RefreshError

from solnexus_ingest.gmail.client import (
    GmailAuthError,
    GmailClient,
    GmailPolicyError,
    GmailRetriesExhausted,
    HistoryExpired,
    RetryPolicy,
)


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
        self.paths.append(url.rsplit("/me", 1)[1])
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(*outcomes, max_retries: int = 5):
    sleeps: list[float] = []
    session = FakeSession(*outcomes)
    gmail = GmailClient(session, RetryPolicy(max_retries=max_retries), sleep=sleeps.append)
    return gmail, session, sleeps


@pytest.mark.parametrize(
    "failure",
    [error(429, "rateLimitExceeded"), error(403, "userRateLimitExceeded"), error(503, "backendError"),
     requests.ConnectionError("reset")],
)
def test_transient_failures_are_retried_then_succeed(failure):
    gmail, session, sleeps = client(failure, response(200, {"emailAddress": "x", "historyId": "1"}))

    assert gmail.get_profile()["historyId"] == "1"
    assert len(session.paths) == 2
    assert len(sleeps) == 1


def test_retries_are_bounded():
    gmail, session, sleeps = client(*[error(503, "backendError")] * 3, max_retries=2)

    with pytest.raises(GmailRetriesExhausted):
        gmail.get_profile()
    assert len(session.paths) == 3  # first try + 2 retries
    assert len(sleeps) == 2


def test_server_retry_after_is_respected():
    gmail, _, sleeps = client(error(429, "rateLimitExceeded", {"Retry-After": "40"}), response(200, {}))

    gmail.get_profile()

    assert sleeps[0] >= 40


def test_backoff_grows_and_is_capped():
    policy = RetryPolicy(base_delay=1, max_delay=32)

    delays = [policy.delay(n) for n in range(8)]

    assert 1 <= delays[0] < 2
    assert 4 <= delays[2] < 5
    assert all(d < 33 for d in delays)  # 32s cap + at most 1s jitter


@pytest.mark.parametrize("failure", [error(403, "domainPolicy"), error(400, "invalidArgument")])
def test_policy_and_request_errors_fail_fast(failure):
    gmail, session, sleeps = client(failure)

    with pytest.raises(GmailPolicyError, match="domainPolicy|invalidArgument"):
        gmail.get_profile()
    assert sleeps == []


@pytest.mark.parametrize("failure", [RefreshError("invalid_grant"), error(401, "authError")])
def test_expired_or_revoked_consent_needs_reauthorization(failure):
    gmail, _, sleeps = client(failure)

    with pytest.raises(GmailAuthError):
        gmail.get_profile()
    assert sleeps == []


def test_expired_history_cursor_is_reported_distinctly():
    gmail, _, _ = client(error(404, "notFound"))

    with pytest.raises(HistoryExpired):
        gmail.list_history("123", None, None)


def test_history_page_returns_unique_added_ids_and_latest_history_id():
    body = {
        "history": [
            {"messagesAdded": [{"message": {"id": "a"}}, {"message": {"id": "b"}}]},
            {"messagesAdded": [{"message": {"id": "a"}}]},
            {"labelsAdded": [{"message": {"id": "c"}}]},
        ],
        "nextPageToken": "p2",
        "historyId": "900",
    }
    gmail, _, _ = client(response(200, body))

    assert gmail.list_history("100", None, None) == (["a", "b"], "p2", "900")


def test_message_deleted_after_listing_returns_none():
    gmail, _, _ = client(error(404, "notFound"))

    assert gmail.get_raw_message("gone") is None


def test_error_messages_do_not_echo_response_bodies():
    leaked = response(400, {"error": {"errors": [{"reason": "badRequest"}], "message": "lead@clinic.example.test"}})
    gmail, _, _ = client(leaked)

    with pytest.raises(GmailPolicyError) as exc_info:
        gmail.get_profile()
    assert "example.test" not in str(exc_info.value)
