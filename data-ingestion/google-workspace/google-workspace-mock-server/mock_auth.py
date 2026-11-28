"""Bearer-token check for the mock's Google-shaped routes.

Google refuses an API call without `Authorization: Bearer <access token>` (401). The mock does the same, so a client
that forgets to authenticate fails here, not only in production. For now any non-empty token is accepted; step 5 adds
the OAuth token endpoint and then accepts only tokens the mock itself issued.
"""

from __future__ import annotations

from fastapi import Header

from google_errors import GoogleApiError


def require_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the bearer token, or a Google-style 401 when it is missing or malformed."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise GoogleApiError(
            401,
            "authError",
            "Request is missing required authentication credential. Expected OAuth 2 access token.",
        )
    return token.strip()
