"""Unit tests for the Gmail client's endpoints, using a fake HTTP session.

Retries and error classification are the shared layer's job (test_google_api.py)."""

from __future__ import annotations

import pytest
import requests

from services.gmail_client import GmailClient, HistoryExpired
from services.google_api import RetryPolicy


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
