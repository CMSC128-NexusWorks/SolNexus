import re

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import require_staff
from app.auth.sessions import SESSION_COOKIE
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


def test_unknown_routes_use_the_contract_error_shape(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found", "details": []}}
