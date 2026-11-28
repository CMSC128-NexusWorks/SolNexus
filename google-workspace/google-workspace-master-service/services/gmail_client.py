"""Thin, read-only Gmail REST client with bounded retries.

Only the four calls the connector needs are wrapped. Errors are classified so the caller can tell
"wait and retry" (quota, transient server errors) from "a person must act" (revoked or expired
consent, admin policy). Error messages carry status codes and Google's reason only: never tokens,
message content or mailbox addresses (NFR redacted logs).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

log = logging.getLogger(__name__)

API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
# Least privilege that can read message bodies (SNX-21 findings).
READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# (connect, read) seconds. Without a timeout a stalled connection would hang the Airflow task forever.
REQUEST_TIMEOUT = (10, 60)

TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
# A 403 with one of these reasons is throttling, not a permission problem.
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
# A 403 with one of these reasons is a used-up daily/project quota: it clears with time, not with an
# operator, but not within seconds either, so the client does not retry it itself.
QUOTA_EXHAUSTED_REASONS = frozenset({"dailyLimitExceeded", "quotaExceeded"})


class GmailError(Exception):
    """Base class for connector-visible Gmail failures."""


class GmailAuthError(GmailError):
    """Consent expired or was revoked (e.g. invalid_grant). Needs re-authorization, not a retry."""


class GmailPolicyError(GmailError):
    """Permanent refusal such as a Workspace domainPolicy or a bad request. Needs a person."""


class GmailQuotaExhausted(GmailError):
    """The daily/project quota is used up. Retry later (Airflow task retries or the next run)."""


class GmailRetriesExhausted(GmailError):
    """A transient failure outlasted the retry budget. Safe to rerun later."""


class HistoryExpired(GmailError):
    """The stored historyId is too old for users.history.list; the caller must run a full sync."""


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter, bounded in both attempts and delay."""

    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 32.0

    def delay(self, retry_number: int, retry_after: float | None = None) -> float:
        """Seconds to wait before retry number retry_number (0-based).

        Jitter spreads retries from concurrent clients apart. A server-supplied Retry-After wins
        when it asks for longer than our own schedule.
        """
        backoff = min(self.max_delay, self.base_delay * 2**retry_number) + random.uniform(0, 1)
        return max(backoff, retry_after or 0.0)


class GmailClient:
    def __init__(
        self,
        session: requests.Session,
        retry_policy: RetryPolicy = RetryPolicy(),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._retry = retry_policy
        self._sleep = sleep  # injectable so tests do not actually wait

    @classmethod
    def from_token_file(cls, token_path: str, **kwargs: Any) -> GmailClient:
        """Client for the mailbox whose OAuth token (authorized-user JSON from SNX-21) is at token_path.

        The access token is refreshed in memory on each run; the file is only read, so it can be
        mounted read-only.
        """
        credentials = Credentials.from_authorized_user_file(token_path, scopes=[READONLY_SCOPE])
        return cls(AuthorizedSession(credentials), **kwargs)

    def get_profile(self) -> dict[str, Any]:
        """The connected mailbox's address and its current historyId."""
        return self._get("/profile")

    def list_message_ids(
        self, query: str | None, label_id: str | None, page_token: str | None
    ) -> tuple[list[str], str | None]:
        """One page of message IDs matching query/label (users.messages.list). Used for full syncs."""
        params = {"q": query, "labelIds": label_id, "pageToken": page_token, "maxResults": 100}
        body = self._get("/messages", params)
        return [m["id"] for m in body.get("messages", [])], body.get("nextPageToken")

    def list_history(
        self, start_history_id: str, label_id: str | None, page_token: str | None
    ) -> tuple[list[str], str | None, str]:
        """One page of IDs of messages added since start_history_id (users.history.list).

        Returns (message_ids, next_page_token, history_id). history_id is the mailbox's latest
        historyId, the cursor to store once every page has been written.
        """
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "labelId": label_id,
            "pageToken": page_token,
            "maxResults": 500,
        }
        try:
            body = self._get("/history", params)
        except _NotFound as exc:
            # Gmail keeps history for a limited time (typically about a week); 404 means the cursor
            # is older than that.
            raise HistoryExpired("stored historyId is no longer available") from exc

        ids: list[str] = []
        for record in body.get("history", []):
            for added in record.get("messagesAdded", []):
                message_id = added["message"]["id"]
                if message_id not in ids:  # one message can appear in several history records
                    ids.append(message_id)
        return ids, body.get("nextPageToken"), body["historyId"]

    def get_raw_message(self, message_id: str) -> dict[str, Any] | None:
        """The message in format=raw, or None if it was deleted after being listed."""
        try:
            return self._get(f"/messages/{message_id}", {"format": "raw"})
        except _NotFound:
            return None

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET with retries for throttling and transient failures; classifies everything else."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for retry_number in range(self._retry.max_retries + 1):
            try:
                response = self._session.get(API_ROOT + path, params=params, timeout=REQUEST_TIMEOUT)
            except RefreshError as exc:
                # Raised while refreshing the access token. google-auth marks token-endpoint outages
                # (5xx, timeouts) retryable; invalid_grant (expired 7-day testing consent, revoked
                # access) is not, and only re-authorization fixes it.
                if not exc.retryable:
                    raise GmailAuthError("OAuth refresh failed; re-authorize the mailbox") from exc
                failure: str = "RefreshError (retryable)"
                retry_after = None
            except (requests.ConnectionError, requests.Timeout, TransportError) as exc:
                failure = type(exc).__name__
                retry_after = None
            else:
                if response.ok:
                    return response.json()
                reason = _error_reason(response)
                if response.status_code == 404:
                    raise _NotFound(path)
                if response.status_code == 401:
                    raise GmailAuthError(f"Gmail rejected the credentials (401 {reason})")
                if response.status_code == 403 and reason in QUOTA_EXHAUSTED_REASONS:
                    raise GmailQuotaExhausted(f"Gmail quota used up (403 {reason})")
                retryable = response.status_code in TRANSIENT_STATUSES or (
                    response.status_code == 403 and reason in RATE_LIMIT_REASONS
                )
                if not retryable:
                    raise GmailPolicyError(f"Gmail refused the request ({response.status_code} {reason})")
                failure = f"{response.status_code} {reason}"
                retry_after = _retry_after_seconds(response)

            if retry_number == self._retry.max_retries:
                raise GmailRetriesExhausted(f"gave up after {retry_number} retries ({failure})")
            wait = self._retry.delay(retry_number, retry_after)
            log.warning("Gmail call failed (%s); retry %d in %.1fs", failure, retry_number + 1, wait)
            self._sleep(wait)
        raise AssertionError("unreachable")  # the loop either returns or raises


class _NotFound(GmailError):
    """Internal: a 404, translated by each caller into what it means for that endpoint."""


def _error_reason(response: requests.Response) -> str:
    """Google's machine-readable error reason (e.g. rateLimitExceeded), or 'unknown'."""
    try:
        errors = response.json()["error"].get("errors") or [{}]
        return str(errors[0].get("reason") or response.json()["error"].get("status") or "unknown")
    except (ValueError, KeyError, TypeError, AttributeError):
        return "unknown"


def _retry_after_seconds(response: requests.Response) -> float | None:
    """Retry-After in seconds when the server sent a numeric value."""
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
