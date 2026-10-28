import hashlib

from app.auth.sessions import SESSION_COOKIE

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


def test_logout_without_session_is_401(client):
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


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


def test_recent_activity_does_not_rewrite_the_session_row(signed_in, run_sql):
    run_sql("UPDATE app.staff_sessions SET last_seen_at = now() - interval '1 minute'")
    [before] = run_sql("SELECT last_seen_at FROM app.staff_sessions")

    signed_in.get("/api/v1/auth/session")

    [after] = run_sql("SELECT last_seen_at FROM app.staff_sessions")
    assert after.last_seen_at == before.last_seen_at


def test_deactivating_an_account_ends_its_sessions(signed_in, staff, run_sql):
    run_sql("UPDATE app.staff_users SET is_active = false WHERE email = :email", email=staff["email"])

    response = signed_in.get("/api/v1/auth/session")

    assert response.status_code == 401
