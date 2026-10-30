import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Every error uses the contract shape {"error": {"code", "message", "details"}}.
# Messages and details never echo request values, which may be passwords or private row content.

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}


class ApiError(Exception):
    """Raise from a route or dependency to return a contract error."""

    def __init__(self, status_code: int, code: str, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def error_response(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


class UnexpectedErrorMiddleware:
    """Turn any uncaught exception into a contract 500, logged server-side with its traceback.

    Starlette's own Exception handler runs in ServerErrorMiddleware, which sits outside CORSMiddleware.
    Its response carries no CORS headers, so the browser would hide it and the dashboard would see a
    network failure instead of a 500. This middleware sits inside CORS (see install_error_handlers).
    The response says only "internal_error": exception text can contain SQL or row values.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def track_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_start)
        except Exception as exc:
            database_error = _database_error_in(exc)
            if database_error is None:
                logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            else:
                # PostgreSQL's DETAIL ("Failing row contains (...)") and SQLAlchemy's [parameters: ...] put
                # whole rows, such as imported client leads or staff emails, into the message. Log where it
                # failed and which constraint, never the message.
                logger.error(
                    "Unhandled database error on %s %s: %s\n%s",
                    scope["method"],
                    scope["path"],
                    _describe_database_error(database_error),
                    "".join(traceback.format_tb(exc.__traceback__)),
                )
            if response_started:
                # Too late to replace the response; let the server close the connection.
                raise
            response = error_response(500, "internal_error", "Something went wrong on the server")
            await response(scope, receive, send)


def _database_error_in(exc: BaseException) -> DBAPIError | None:
    """The first database error in exc's cause/context chain, since a later error can wrap one."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, DBAPIError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _describe_database_error(error: DBAPIError) -> str:
    """Error class, SQLSTATE, table and constraint: enough to debug, with no row values."""
    original = error.orig
    diag = getattr(original, "diag", None)
    parts = [type(original).__name__ if original is not None else type(error).__name__]
    for label, value in (
        ("sqlstate", getattr(original, "sqlstate", None)),
        ("table", getattr(diag, "table_name", None)),
        ("constraint", getattr(diag, "constraint_name", None)),
    ):
        if value:
            parts.append(f"{label}={value}")
    return " ".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    """Call before adding CORSMiddleware: middleware added later wraps it, so CORS stays outermost."""
    app.add_middleware(UnexpectedErrorMiddleware)

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # loc is ("body", "email") or ("query", "limit"); drop the location kind. Never include "input".
        details = [
            {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(422, "validation_error", "Request validation failed", details)
