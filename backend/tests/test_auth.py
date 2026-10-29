import asyncio
import hashlib
import json

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.dependencies import require_staff
from app.auth.sessions import SESSION_COOKIE
from app.db import Db
from app.errors import ApiError, install_error_handlers
from app.main import app

INVALID_CREDENTIALS = {
    "error": {"code": "invalid_credentials", "message": "Invalid email or password", "details": []}
}
UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "Sign in required", "details": []}}


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# Login


def test_login_returns_staff_summary_and_sets_session_cookie(client, staff):
    response = login(client, staff["email"], staff["password"])

    assert response.status_code == 200
    assert response.json() == {"user_id": staff["user_id"], "email": staff["email"]}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api"):
        assert attribute in cookie


def test_login_ignores_email_case(client, staff):
    response = login(client, staff["email"].upper(), staff["password"])

    assert response.status_code == 200


def test_wrong_password_gets_generic_401_and_no_cookie(client, staff):
    response = login(client, staff["email"], "wrong password")

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS
    assert "set-cookie" not in response.headers


def test_unknown_email_gets_the_same_401_as_a_wrong_password(client, staff):
    response = login(client, "nobody@example.test", staff["password"])

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_deactivated_account_cannot_sign_in(client, staff, run_sql):
    run_sql("UPDATE app.staff_users SET is_active = false WHERE email = :email", email=staff["email"])

    response = login(client, staff["email"], staff["password"])

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_seeded_placeholder_hash_never_matches(client, run_sql):
    # backend/fixtures/dev_seed.sql stores unusable hashes; they must fail cleanly, not crash.
    run_sql(
        "INSERT INTO app.staff_users (email, password_hash) VALUES (:email, '$dev-seed$login-disabled')",
        email="seeded@example.test",
    )

    response = login(client, "seeded@example.test", "anything at all")

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_login_commits_the_session_before_the_response_starts(staff, run_sql):
    # TestClient waits for the whole ASGI call, so it can't see this ordering. Drive the app directly
    # and look at the database, from another connection, the moment the response starts.
    body = json.dumps({"email": staff["email"], "password": staff["password"]}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/auth/login",
        "raw_path": b"/api/v1/auth/login",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("testclient", 50000),
        "server": ("testserver", 443),
    }
    seen = {}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
            seen["sessions_committed"] = len(run_sql("SELECT 1 FROM app.staff_sessions"))

    asyncio.run(app(scope, receive, send))

    assert seen == {"status": 200, "sessions_committed": 1}


def test_database_stores_only_a_hash_of_the_session_token(client, staff, run_sql):
    login(client, staff["email"], staff["password"])
    token = client.cookies[SESSION_COOKIE]

    rows = run_sql("SELECT token_sha256 FROM app.staff_sessions")

    assert len(rows) == 1
    assert bytes(rows[0].token_sha256) == hashlib.sha256(token.encode()).digest()


# Current session


def test_session_without_cookie_is_401(client):
    response = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_session_with_unknown_token_is_401(client):
    response = client.get("/api/v1/auth/session", headers={"Cookie": f"{SESSION_COOKIE}=not-a-real-token"})

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_session_returns_the_signed_in_staff_member(signed_in, staff):
    response = signed_in.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {"user_id": staff["user_id"], "email": staff["email"]}


# Logout


def test_logout_ends_the_session_on_the_server(signed_in):
    token = signed_in.cookies[SESSION_COOKIE]

    response = signed_in.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert 'Max-Age=0' in response.headers["set-cookie"]
    # Replaying the old cookie, as a copied or stolen one would be, no longer works.
    replay = signed_in.get("/api/v1/auth/session", headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    assert replay.status_code == 401


def test_logout_without_a_session_still_clears_the_cookie(client):
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_logout_after_the_session_expired_still_clears_the_cookie(signed_in, run_sql):
    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '8 hours 1 second'")

    response = signed_in.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_logout_twice_is_harmless(signed_in):
    assert signed_in.post("/api/v1/auth/logout").status_code == 204
    assert signed_in.post("/api/v1/auth/logout").status_code == 204


# Expiry: 8 hours idle, 7 days absolute


def test_session_expires_after_8_hours_without_activity(signed_in, run_sql):
    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '8 hours 1 second'")

    response = signed_in.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_session_expires_after_7_days_even_when_active(signed_in, run_sql):
    run_sql(
        "UPDATE app.staff_sessions SET created_at = now() - interval '7 days 1 second', "
        "expires_at = now() - interval '1 second', last_seen_at = now()"
    )

    response = signed_in.get("/api/v1/auth/session")

    assert response.status_code == 401


def test_activity_extends_the_idle_window(signed_in, run_sql):
    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '7 hours'")

    assert signed_in.get("/api/v1/auth/session").status_code == 200

    [row] = run_sql("SELECT now() - last_seen_at < interval '1 minute' AS refreshed FROM app.staff_sessions")
    assert row.refreshed


def test_every_request_restarts_the_idle_window(signed_in, run_sql):
    # No refresh throttle: a request 4 minutes after the last one still counts, so the session ends
    # exactly 8 hours after the latest request.
    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '4 minutes'")

    signed_in.get("/api/v1/auth/session")

    [row] = run_sql("SELECT now() - last_seen_at < interval '1 minute' AS refreshed FROM app.staff_sessions")
    assert row.refreshed


def test_a_request_that_fails_still_counts_as_activity(signed_in, run_sql):
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/api/v1/missing", dependencies=[Depends(require_staff)])
    def missing(conn: Db):
        # Writes in the request transaction are rolled back by this error; the refresh must not be.
        conn.execute(text("SELECT 1"))
        raise ApiError(404, "not_found", "No such lead")

    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '7 hours'")
    token = signed_in.cookies[SESSION_COOKIE]

    with TestClient(probe, base_url="https://testserver") as client:
        response = client.get("/api/v1/missing", headers={"Cookie": f"{SESSION_COOKIE}={token}"})

    assert response.status_code == 404
    [row] = run_sql("SELECT now() - last_seen_at < interval '1 minute' AS refreshed FROM app.staff_sessions")
    assert row.refreshed


def test_deactivating_an_account_ends_its_sessions(signed_in, staff, run_sql):
    run_sql("UPDATE app.staff_users SET is_active = false WHERE email = :email", email=staff["email"])

    response = signed_in.get("/api/v1/auth/session")

    assert response.status_code == 401
