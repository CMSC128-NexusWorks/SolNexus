"""Injected delays and failures: make the mock slow or failing on purpose, to test the master's recovery paths.

Real Google throttles (429, 403 rateLimitExceeded), runs out of daily quota (403 dailyLimitExceeded), has outages
(500, 503), lets access tokens expire (401) and revokes consent (invalid_grant). Those paths are where ingestion
code usually breaks, and they are nearly impossible to trigger on demand against the real service. Here a test
schedules them: "the next 2 Gmail calls answer 429", "every Calendar call takes 300 ms".

A fault is scheduled per target (gmail, calendar or token) with a count, and each matching request consumes one,
in the order they were scheduled. When the count reaches zero the fault is gone and requests succeed again, which
is exactly what a client's retry-with-backoff should ride out. Step 6 exposes this over HTTP (/_mock/faults);
until then tests drive it through the state directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, get_args

from fastapi import Request

from google_errors import GoogleApiError, OAuthTokenError

FaultTarget = Literal["gmail", "calendar", "token"]
FaultKind = Literal[
    "rate_limit",
    "user_rate_limit",
    "daily_quota",
    "backend_error",
    "service_unavailable",
    "expired_access_token",
    "invalid_grant",
    "token_server_error",
]
FAULT_TARGETS: tuple[str, ...] = get_args(FaultTarget)

# What each API fault answers with: (HTTP status, Google reason, message), as Google sends them.
API_FAULT_RESPONSES: dict[str, tuple[int, str, str]] = {
    # Throttling: the master retries these with backoff.
    "rate_limit": (429, "rateLimitExceeded", "Rate Limit Exceeded"),
    "user_rate_limit": (403, "userRateLimitExceeded", "User Rate Limit Exceeded"),
    # Quota used up for the day: not worth retrying within seconds; the master fails the run as quota-exhausted.
    "daily_quota": (403, "dailyLimitExceeded", "Daily Limit Exceeded"),
    # Outages: retried with backoff.
    "backend_error": (500, "backendError", "Backend Error"),
    "service_unavailable": (503, "backendError", "Service Unavailable"),
    # The access token expired mid-run: google-auth's session refreshes it and repeats the call by itself.
    "expired_access_token": (401, "authError", "Request had invalid authentication credentials."),
}
# What each token-endpoint fault answers with, in OAuth's format. google-auth treats invalid_grant as permanent
# (re-consent needed) and a 500 with internal_failure as retryable.
TOKEN_FAULT_RESPONSES: dict[str, tuple[int, str, str]] = {
    "invalid_grant": (400, "invalid_grant", "Token has been expired or revoked."),
    "token_server_error": (500, "internal_failure", "Backend Error"),
}


@dataclass
class ScheduledFault:
    """`remaining` upcoming requests to `target` fail with `kind`."""

    target: FaultTarget
    kind: FaultKind
    remaining: int
    # Sent as a Retry-After header (seconds) with rate-limit answers, when set.
    retry_after_seconds: int | None = None


class FaultPlan:
    """The delays and scheduled failures currently in force. Read and changed under the state's lock."""

    def __init__(self, default_delay_ms: int = 0) -> None:
        # Applies to every target unless a per-target delay overrides it (MOCK_RESPONSE_DELAY_MS).
        self.default_delay_ms = default_delay_ms
        self.delay_ms_by_target: dict[str, int] = {}
        self.scheduled: list[ScheduledFault] = []

    def schedule(self, fault: ScheduledFault) -> None:
        """Add a fault after any already scheduled. An API fault on the token endpoint (or the reverse) is refused,
        because each speaks a different error format and the combination could never happen with Google."""
        allowed = TOKEN_FAULT_RESPONSES if fault.target == "token" else API_FAULT_RESPONSES
        if fault.kind not in allowed:
            raise ValueError(f"fault {fault.kind!r} does not apply to target {fault.target!r}")
        if fault.remaining < 1:
            raise ValueError("a fault must apply to at least one request")
        self.scheduled.append(fault)

    def take_next_fault(self, target: str) -> ScheduledFault | None:
        """The first scheduled fault for this target, consuming one of its uses (and dropping it when used up)."""
        for fault in self.scheduled:
            if fault.target == target:
                fault.remaining -= 1
                if fault.remaining == 0:
                    self.scheduled.remove(fault)
                return fault
        return None

    def delay_seconds_for(self, target: str) -> float:
        return self.delay_ms_by_target.get(target, self.default_delay_ms) / 1000


def error_for_fault(fault: ScheduledFault) -> Exception:
    """The exception that makes the route answer as Google would for this fault."""
    if fault.target == "token":
        code, error, description = TOKEN_FAULT_RESPONSES[fault.kind]
        return OAuthTokenError(code, error, description)
    code, reason, message = API_FAULT_RESPONSES[fault.kind]
    headers = {"Retry-After": str(fault.retry_after_seconds)} if fault.retry_after_seconds and code == 429 else None
    return GoogleApiError(code, reason, message, headers=headers)


def apply_scheduled_faults(target: FaultTarget) -> Callable[[Request], Awaitable[None]]:
    """A FastAPI dependency for one target: wait the configured delay, then fail if a fault is scheduled.

    The delay is awaited (asyncio.sleep), not slept on a worker thread, so a slow mock does not tie up the thread
    pool that the plain `def` routes run on.
    """

    async def wait_then_maybe_fail(request: Request) -> None:
        state = request.app.state.mock_google_state
        with state.lock:
            delay_seconds = state.faults.delay_seconds_for(target)
            fault = state.faults.take_next_fault(target)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        if fault is not None:
            raise error_for_fault(fault)

    return wait_then_maybe_fail
