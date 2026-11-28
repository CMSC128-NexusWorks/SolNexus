"""Fake Google OAuth: the token endpoint the master's credentials refresh against, and the access check on every call.

SolNexus authorizes Google with an "authorized user" token file from the SNX-21 consent flow: a client ID, client
secret and long-lived refresh token. google-auth trades the refresh token for a short-lived access token at the file's
`token_uri` (Google's is https://oauth2.googleapis.com/token), then sends `Authorization: Bearer <access token>` on
every API call and refreshes again when the token expires (a 401). The mock implements both halves:

- POST /token (refresh_token grant only) issues access tokens, or answers in OAuth's error format:
  invalid_client (wrong client), invalid_grant (wrong, expired or revoked refresh token), invalid_scope.
- Gmail and Calendar accept only access tokens the mock issued, not yet expired, and carrying a scope that API
  accepts. A token without a Calendar scope gets 403 insufficientPermissions on Calendar, which is exactly what
  happens when the mailbox was consented for Gmail only and never re-consented for Calendar.

The client ID, secret and refresh token below are fixed, public, fake values: they unlock nothing but this mock, and
the mock only runs in local, ci and dev (mock_settings).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, Request

from google_errors import GoogleApiError, OAuthTokenError
from mock_faults import apply_scheduled_faults

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_EVENTS_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
KNOWN_SCOPES = frozenset({GMAIL_READONLY_SCOPE, CALENDAR_EVENTS_READONLY_SCOPE, CALENDAR_READONLY_SCOPE})
# Which scopes let a token call which API (any one of them is enough), as Google enforces it.
SCOPES_ACCEPTED_BY_API: dict[str, frozenset[str]] = {
    "gmail": frozenset({GMAIL_READONLY_SCOPE}),
    "calendar": frozenset({CALENDAR_EVENTS_READONLY_SCOPE, CALENDAR_READONLY_SCOPE}),
}
# The least-privilege pair the calendar contract asks for: what the mock grants unless told otherwise.
DEFAULT_GRANTED_SCOPES = (GMAIL_READONLY_SCOPE, CALENDAR_EVENTS_READONLY_SCOPE)

MOCK_CLIENT_ID = "solnexus-mock-client.apps.example.test"
MOCK_CLIENT_SECRET = "mock-client-secret-not-a-real-secret"
MOCK_REFRESH_TOKEN = "mock-refresh-token-not-a-real-secret"

ApiName = Literal["gmail", "calendar"]


@dataclass(frozen=True)
class IssuedAccessToken:
    token: str
    scopes: frozenset[str]
    expires_at: datetime


class MockOAuthServer:
    """Issued access tokens and the one refresh token's status. Read and changed under the state's lock."""

    def __init__(self, granted_scopes: frozenset[str], access_token_ttl_seconds: int) -> None:
        # What the (single) refresh token was consented for.
        self.granted_scopes = granted_scopes
        self.access_token_ttl_seconds = access_token_ttl_seconds
        self.issued: dict[str, IssuedAccessToken] = {}
        # Set by a control route (step 6) to simulate the user revoking access: every refresh then fails.
        self.refresh_token_revoked = False

    def issue_access_token(self, scopes: frozenset[str], now: datetime) -> IssuedAccessToken:
        """Mint an access token. "ya29." is the prefix real Google access tokens carry."""
        issued = IssuedAccessToken(
            token=f"ya29.mock-{secrets.token_urlsafe(24)}",
            scopes=scopes,
            expires_at=now + timedelta(seconds=self.access_token_ttl_seconds),
        )
        self.issued[issued.token] = issued
        return issued

    def exchange_refresh_token(self, form: dict[str, str], now: datetime) -> IssuedAccessToken:
        """The refresh_token grant, with the same checks and error codes as Google's token endpoint."""
        if form.get("grant_type") != "refresh_token":
            raise OAuthTokenError(400, "unsupported_grant_type", f"Invalid grant_type: {form.get('grant_type', '')}")
        if form.get("client_id") != MOCK_CLIENT_ID or form.get("client_secret") != MOCK_CLIENT_SECRET:
            raise OAuthTokenError(401, "invalid_client", "The OAuth client was not found.")
        if form.get("refresh_token") != MOCK_REFRESH_TOKEN or self.refresh_token_revoked:
            # Same answer for a wrong token and a revoked one, as with Google: the client must re-consent either way.
            raise OAuthTokenError(400, "invalid_grant", "Token has been expired or revoked.")
        requested = frozenset(form.get("scope", "").split())
        if requested and not requested <= self.granted_scopes:
            raise OAuthTokenError(400, "invalid_scope", "Some requested scopes were not granted.")
        # Without an explicit scope request, the token carries everything the refresh token was granted.
        return self.issue_access_token(requested or self.granted_scopes, now)

    def check_access_token(self, token: str, api: ApiName, now: datetime) -> None:
        """Accept the call, or raise the 401/403 Google would send for this token."""
        issued = self.issued.get(token)
        if issued is None or now >= issued.expires_at:
            # Unknown and expired look the same to a client: refresh and try again.
            raise GoogleApiError(401, "authError", "Request had invalid authentication credentials.")
        if not issued.scopes & SCOPES_ACCEPTED_BY_API[api]:
            raise GoogleApiError(403, "insufficientPermissions", "Request had insufficient authentication scopes.")


router = APIRouter()


@router.post("/token", dependencies=[Depends(apply_scheduled_faults("token"))])
async def exchange_token(request: Request) -> dict[str, str | int]:
    """OAuth token endpoint (form-encoded body, as google-auth sends it).

    The body is parsed with the standard library rather than FastAPI's Form(), which would pull in an extra
    multipart dependency for four plain fields.
    """
    form = {key: values[-1] for key, values in parse_qs((await request.body()).decode()).items()}
    state = request.app.state.mock_google_state
    with state.lock:
        now = state.clock()
        issued = state.oauth.exchange_refresh_token(form, now)
    return {
        "access_token": issued.token,
        "expires_in": int((issued.expires_at - now).total_seconds()),
        "scope": " ".join(sorted(issued.scopes)),
        "token_type": "Bearer",
    }


def require_access_token_for(api: ApiName) -> Callable[..., None]:
    """A FastAPI dependency for one API: the request must carry a valid bearer token with a scope for that API."""

    def check_bearer_token(request: Request, authorization: str | None = Header(default=None)) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise GoogleApiError(
                401,
                "authError",
                "Request is missing required authentication credential. Expected OAuth 2 access token.",
            )
        state = request.app.state.mock_google_state
        with state.lock:
            state.oauth.check_access_token(token.strip(), api, state.clock())

    return check_bearer_token
