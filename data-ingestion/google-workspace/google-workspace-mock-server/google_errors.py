"""Errors in Google's own JSON format, for the mock's Google-shaped routes.

The master classifies failures by Google's status code and `errors[0].reason` (e.g. 403 rateLimitExceeded is a
retry, 403 domainPolicy needs a person). For the mock to test that logic, its Gmail and Calendar routes must fail
exactly the way Google does, body included. The mock's own `/_mock/*` routes keep the simpler envelope instead.

Shape (Gmail v1 / Calendar v3 error responses):
    {"error": {"code": 404, "message": "...", "errors": [{"message": "...", "domain": "global", "reason": "notFound"}],
               "status": "NOT_FOUND"}}
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

# Google's canonical status names. Older-style errors (e.g. Calendar's 410) carry no status, so it is optional.
GOOGLE_STATUS_BY_CODE = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    429: "RESOURCE_EXHAUSTED",
    500: "INTERNAL",
    503: "UNAVAILABLE",
}


class GoogleApiError(Exception):
    """Raised by a Google-shaped route to answer with a Google error. Handled in mock_app."""

    def __init__(self, code: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.message = message


def google_error_body(code: int, reason: str, message: str) -> dict[str, Any]:
    """The JSON body Google returns for an error with this code and reason."""
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "errors": [{"message": message, "domain": "global", "reason": reason}],
    }
    if code in GOOGLE_STATUS_BY_CODE:
        error["status"] = GOOGLE_STATUS_BY_CODE[code]
    return {"error": error}


def google_error_response(code: int, reason: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content=google_error_body(code, reason, message))
