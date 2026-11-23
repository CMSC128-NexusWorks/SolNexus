import re

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.dependencies import require_staff
from app.auth.sessions import SESSION_COOKIE
from app.db import engine
from app.errors import install_error_handlers
from app.main import app

# The only /api operations reachable without a session. Adding to this set is a security decision:
# say why in the PR.
PUBLIC_API_OPERATIONS = {
    ("POST", "/api/v1/auth/login"),
    # Idempotent and must work after the session expired, so it can always clear the cookie.
    ("POST", "/api/v1/auth/logout"),
}


def test_every_api_operation_rejects_requests_without_a_session(client):
    # Protection is opt-in: a route must sit on the `protected` router in app.main or depend on
    # require_staff itself. A route added straight to `app`, the usual FastAPI pattern, would serve
    # lead data without a session, so this calls every operation in the real app with no cookie.
    # It is black-box on purpose: the OpenAPI schema is FastAPI's public list of operations, while
    # app.routes internals change between releases. Path parameters get a dummy value; require_staff
    # runs before path or body validation, so a protected route answers 401 rather than 422.
    open_operations = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method in operations:
            response = client.request(method.upper(), re.sub(r"\{[^}]+\}", "x", path))
            if response.status_code != 401:
                open_operations.add((method.upper(), path))

    assert open_operations == PUBLIC_API_OPERATIONS


def protected_probe_app() -> FastAPI:
    """A minimal app using the same pattern as app.main: a router guarded by require_staff."""
    probe = FastAPI()
    install_error_handlers(probe)
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_staff)])

    @router.get("/probe")
    def read_probe():
        return {"lead": "private data"}

    probe.include_router(router)
    return probe


def test_protected_routes_reject_requests_without_a_session():
    with TestClient(protected_probe_app(), base_url="https://testserver") as probe:
        response = probe.get("/api/v1/probe")

    assert response.status_code == 401
    assert "private data" not in response.text


def test_protected_routes_allow_a_signed_in_staff_member(signed_in):
    token = signed_in.cookies[SESSION_COOKIE]

    with TestClient(protected_probe_app(), base_url="https://testserver") as probe:
        response = probe.get("/api/v1/probe", headers={"Cookie": f"{SESSION_COOKIE}={token}"})

    assert response.status_code == 200


def test_cors_allows_the_configured_frontend_with_credentials(client):
    response = client.options(
        "/api/v1/auth/session",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_allow_other_origins(client):
    response = client.options(
        "/api/v1/auth/session",
        headers={"Origin": "https://elsewhere.example.test", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_validation_errors_use_the_contract_error_shape(client):
    response = client.post("/api/v1/auth/login", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert {detail["field"] for detail in body["error"]["details"]} == {"email", "password"}


def test_unexpected_errors_return_a_contract_500_the_browser_can_read(client, monkeypatch):
    # Simulates the database failing mid-request, e.g. during the session lookup.
    def database_down(*_args, **_kwargs):
        raise RuntimeError("connection to server failed: SELECT ... FROM app.staff_sessions")

    monkeypatch.setattr("app.auth.dependencies.find_session_user", database_down)

    response = client.get(
        "/api/v1/auth/session",
        headers={"Cookie": f"{SESSION_COOKIE}=some-token", "Origin": "http://localhost:5173"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on the server", "details": []}
    }
    # Without CORS headers the browser would hide the 500 and report a network error.
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "staff_sessions" not in response.text


def test_database_errors_are_logged_without_row_values(client, monkeypatch, caplog):
    # A real constraint failure: PostgreSQL's DETAIL repeats the whole failing row, and SQLAlchemy's
    # message adds the bound parameters. Neither may reach the log.
    def failing_insert(*_args, **_kwargs):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO app.clinics (clinic_name, contact_number, origin) VALUES (:name, :phone, 'bogus')"),
                {"name": "Private Clinic Name", "phone": "0917 PRIVATE"},
            )

    monkeypatch.setattr("app.auth.dependencies.find_session_user", failing_insert)

    with caplog.at_level("WARNING", logger="app.errors"):
        response = client.get("/api/v1/auth/session", headers={"Cookie": f"{SESSION_COOKIE}=some-token"})

    # The SQLAlchemyError handler answers; a check violation is a code or operator problem, so 500.
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    logged = caplog.text
    assert "CheckViolation sqlstate=23514 table=clinics constraint=clinics_origin_check" in logged
    assert "Private Clinic Name" not in logged and "0917 PRIVATE" not in logged


def test_unknown_routes_use_the_contract_error_shape(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found", "details": []}}
