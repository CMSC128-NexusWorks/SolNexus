"""The Google REST layer every Google Workspace client shares: OAuth session, bounded retries, error classes.

Gmail and Calendar fail the same way, because both sit behind Google's common API front end: the same
status codes, the same error reasons, the same OAuth token refresh. So retrying and classifying live
here once. Each product client (gmail_client, and later calendar_client) adds only its endpoints and
what a 404 means for each of them.

Errors are classified so the caller can tell "wait and retry" (quota, transient server errors) from
"a person must act" (revoked or expired consent, admin policy). Error messages carry status codes and
Google's reason only: never tokens, message content or mailbox addresses (NFR redacted logs).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import requests
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

log = logging.getLogger(__name__)

# (connect, read) seconds. Without a timeout a stalled connection would hang the scan forever.
REQUEST_TIMEOUT = (10, 60)

TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
# A 403 with one of these reasons is throttling, not a permission problem.
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
# A 403 with one of these reasons is a used-up daily/project quota: it clears with time, not with an
# operator, but not within seconds either, so the client does not retry it itself.
QUOTA_EXHAUSTED_REASONS = frozenset({"dailyLimitExceeded", "quotaExceeded"})


class GoogleApiError(Exception):
    """Base class for caller-visible Google API failures."""


class GoogleAuthError(GoogleApiError):
    """Consent expired or was revoked (e.g. invalid_grant). Needs re-authorization, not a retry."""


class GooglePolicyError(GoogleApiError):
    """Permanent refusal such as a Workspace domainPolicy or a bad request. Needs a person."""


class GoogleQuotaExhausted(GoogleApiError):
    """The daily/project quota is used up. Retry later (the next run, or the orchestrator's retries)."""


class GoogleRetriesExhausted(GoogleApiError):
    """A transient failure outlasted the retry budget. Safe to rerun later."""


class GoogleNotFound(GoogleApiError):
    """A 404. Deliberately generic: each product client translates it into what it means for that call
    (Gmail: a deleted message or an expired historyId; Calendar: an expired sync token is a 410 instead)."""


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


def authorized_session(token_path: str, scopes: Sequence[str]) -> AuthorizedSession:
    """An HTTP session for the account whose OAuth token (authorized-user JSON from SNX-21) is at token_path.

    The access token is refreshed in memory as needed; the file is only read, so it can be mounted
    read-only. scopes must be ones the token was granted, or Google refuses the refresh.
    """
    credentials = Credentials.from_authorized_user_file(token_path, scopes=list(scopes))
    return AuthorizedSession(credentials)


class GoogleApi:
    """GET against one Google API root, with retries for throttling and transient failures."""

    def __init__(
        self,
        session: requests.Session,
        api_root: str,
        api_name: str,
        retry_policy: RetryPolicy = RetryPolicy(),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._root = api_root
        # Used in log lines and error messages ("Gmail refused the request ..."), so operators can tell
        # which product failed without a stack trace.
        self._name = api_name
        self._retry = retry_policy
        self._sleep = sleep  # injectable so tests do not actually wait

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET api_root + path; returns the JSON body or raises a classified GoogleApiError."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for retry_number in range(self._retry.max_retries + 1):
            try:
                response = self._session.get(self._root + path, params=params, timeout=REQUEST_TIMEOUT)
            except RefreshError as exc:
                # Raised while refreshing the access token. google-auth marks token-endpoint outages
                # (5xx, timeouts) retryable; invalid_grant (expired 7-day testing consent, revoked
                # access) is not, and only re-authorization fixes it.
                if not exc.retryable:
                    raise GoogleAuthError("OAuth refresh failed; re-authorize the account") from exc
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
                    raise GoogleNotFound(f"{self._name} 404 {reason}")
                if response.status_code == 401:
                    raise GoogleAuthError(f"{self._name} rejected the credentials (401 {reason})")
                if response.status_code == 403 and reason in QUOTA_EXHAUSTED_REASONS:
                    raise GoogleQuotaExhausted(f"{self._name} quota used up (403 {reason})")
                retryable = response.status_code in TRANSIENT_STATUSES or (
                    response.status_code == 403 and reason in RATE_LIMIT_REASONS
                )
                if not retryable:
                    raise GooglePolicyError(f"{self._name} refused the request ({response.status_code} {reason})")
                failure = f"{response.status_code} {reason}"
                retry_after = _retry_after_seconds(response)

            if retry_number == self._retry.max_retries:
                raise GoogleRetriesExhausted(f"gave up after {retry_number} retries ({failure})")
            wait = self._retry.delay(retry_number, retry_after)
            log.warning("%s call failed (%s); retry %d in %.1fs", self._name, failure, retry_number + 1, wait)
            self._sleep(wait)
        raise AssertionError("unreachable")  # the loop either returns or raises


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
