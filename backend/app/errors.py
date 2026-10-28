from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Every error uses the contract shape {"error": {"code", "message", "details"}}.
# Messages and details never echo request values, which may be passwords or private row content.

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


def install_error_handlers(app: FastAPI) -> None:
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
