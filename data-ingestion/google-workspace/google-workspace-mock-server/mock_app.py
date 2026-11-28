"""The mock Google server's FastAPI app: a fake Gmail and Calendar API with synthetic data (SNX-69).

The master service talks to it exactly as it talks to Google, so the whole pipeline can run locally and
in CI with no Google account and no secrets. So far it has validated settings, a validated dataset loaded
into in-memory state (mock_state), the health route, the error formats and the Gmail API (routes_gmail).
Calendar and the OAuth token endpoint arrive in later steps.

Route namespaces:
- `/_mock/*` holds the mock's own routes (health now; data control and fault injection later). The
  underscore prefix can never collide with a real Google path, and it makes a test's intent obvious.
- Google-shaped paths (e.g. `/gmail/v1/...`) mirror Google's URLs and return Google's error format
  (google_errors), so the master's real error classification is what gets tested.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TextIO

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import routes_gmail
from google_errors import GoogleApiError, google_error_response
from mock_dataset import read_dataset_or_problems
from mock_settings import MockServerSettings, format_startup_report, load_mock_server_settings_or_exit
from mock_state import MockGoogleState, find_unplayable_dataset_parts

log = logging.getLogger("google_workspace_mock")

# Stable, machine-readable codes for the error envelope. Anything else becomes HTTP_<status>.
ERROR_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_FAILED",
    500: "INTERNAL_ERROR",
}


def error_envelope(status: int, message: str) -> JSONResponse:
    """The mock's error response: {"success": false, "error": CODE, "message": ..., "status": N}.

    Used for the mock's own routes. It never includes a stack trace or exception text, so nothing internal
    leaks to a caller. (Google-shaped routes answer in Google's own error format instead.)
    """
    code = ERROR_CODE_BY_STATUS.get(status, f"HTTP_{status}")
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": code, "message": message, "status": status},
    )


def is_mock_control_path(path: str) -> bool:
    """The mock's own routes (`/_mock/*`) use the envelope; every other path imitates Google."""
    return path == "/_mock" or path.startswith("/_mock/")


def register_error_handlers(app: FastAPI) -> None:
    """Answer every error in the caller's dialect: the envelope on /_mock/*, Google's format everywhere else.

    No handler ever returns exception text or a stack trace; those stay in the mock's log.
    """

    @app.exception_handler(GoogleApiError)
    async def google_api_error(_: Request, exc: GoogleApiError) -> JSONResponse:
        return google_error_response(exc.code, exc.reason, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Unknown paths (404) and wrong methods (405), plus errors raised by route code.
        if is_mock_control_path(request.url.path):
            return error_envelope(exc.status_code, str(exc.detail))
        reason = "notFound" if exc.status_code == 404 else "invalid"
        return google_error_response(exc.status_code, reason, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        if is_mock_control_path(request.url.path):
            # A count, not FastAPI's detail list: the details can echo the submitted values back.
            return error_envelope(422, f"request failed validation ({len(exc.errors())} problem(s))")
        # Google answers a bad query parameter with 400 invalidArgument naming the parameter, not 422.
        first_location = exc.errors()[0]["loc"] if exc.errors() else ()
        parameter = str(first_location[-1]) if first_location else "request"
        return google_error_response(400, "invalidArgument", f"Invalid value for {parameter}.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback in the server log for debugging; the caller gets a generic message only.
        log.exception("Unhandled error in the mock (%s)", type(exc).__name__)
        if is_mock_control_path(request.url.path):
            return error_envelope(500, "the mock hit an unexpected error; see its log")
        return google_error_response(500, "backendError", "Backend Error")


def load_mock_google_state_or_exit(settings: MockServerSettings, stderr: TextIO = sys.stderr) -> MockGoogleState:
    """Read the selected dataset, check it fully (schema, then a dry run of every scripted change) and seed
    the state. On any problem: print every problem in the startup report and exit 1, like bad settings."""
    dataset, problems = read_dataset_or_problems(settings.dataset_path)
    if dataset is not None:
        problems = find_unplayable_dataset_parts(dataset, settings.dataset_path.name)
    if problems:
        stderr.write(format_startup_report(problems))
        sys.exit(1)
    assert dataset is not None
    return MockGoogleState(dataset)


def build_mock_google_app(settings: MockServerSettings, state: MockGoogleState) -> FastAPI:
    """Build the app from validated settings and seeded state. Tests call this directly with their own."""
    app = FastAPI(
        title="SolNexus mock Google (Gmail + Calendar)",
        description="Fake Google Workspace APIs with synthetic data, for local runs and CI. Never for real data.",
        # The interactive docs are handy for exploring the mock; it holds no real data to protect.
        docs_url="/_mock/docs",
        openapi_url="/_mock/openapi.json",
        redoc_url=None,
    )
    register_error_handlers(app)
    # Routes reach the state through app.state, so tests can build an app around any state they like.
    app.state.mock_google_state = state
    app.include_router(routes_gmail.router)

    @app.get("/_mock/health")
    def mock_health() -> dict[str, str]:
        """Liveness for Compose and Docker HEALTHCHECK; also shows which environment this mock runs in."""
        return {"status": "ok", "environment": settings.environment, "dataset": settings.dataset_name}

    return app


def build_mock_google_app_from_environment() -> FastAPI:
    """Uvicorn entry point (`uvicorn --factory mock_app:build_mock_google_app_from_environment`).

    Validates configuration first: on any invalid setting it prints the full report and exits with status
    1 before the server starts listening.
    """
    settings = load_mock_server_settings_or_exit(os.environ)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    state = load_mock_google_state_or_exit(settings)
    # Counts only: dataset content (addresses, subjects) never goes to the log.
    log.info(
        "Mock Google server starting (environment=%s, dataset=%s, messages=%d, events=%d)",
        settings.environment,
        settings.dataset_name,
        len(state.mailbox.messages),
        len(state.calendar.events),
    )
    return build_mock_google_app(settings, state)
