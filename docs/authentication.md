# Staff sign-in and sessions

How the two SolTech staff accounts sign in and how the API protects lead data (FR-10, NFR-03; SNX-27). The endpoint shapes are in the [data/API contract](contracts/phase1-data-api-v1.md#api-shape-proposed-apiv1).

## How it works

1. Staff sign in with email and password at `POST /api/v1/auth/login`.
2. The API checks the password against an Argon2 hash in `app.staff_users`, creates a row in `app.staff_sessions`, and returns a session cookie.
3. The browser sends the cookie with every API request. Every endpoint except login, logout and `/health` looks the session up and returns `401` if it is missing, expired, revoked, or belongs to a deactivated account.
4. On load, the dashboard calls `GET /api/v1/auth/session` to learn who is signed in, because JavaScript cannot read the cookie. Any `401` afterwards sends the user back to sign-in.
5. `POST /api/v1/auth/logout` revokes the session row, so a copied cookie stops working too. It needs no live session and always returns `204` with a cookie-clearing header, so signing out after the session expired still clears the browser's cookie.

The cookie holds a random 256-bit token. The database stores only its SHA-256 hash, so a database leak does not leak usable sessions.

| Rule | Value |
|---|---|
| Idle timeout | 8 hours without an API request |
| Absolute timeout | 7 days after sign-in, however active |
| Idle window refresh | At most once every 5 minutes, so reads don't write on every request |
| Wrong password, unknown email, deactivated account | Same `401 invalid_credentials` response |
| Password length | At least 12 characters |
| Password reset | Signs the account out everywhere |

## Cookie

`solnexus_session`, with `HttpOnly`, `Secure`, `SameSite=Lax` and `Path=/api`.

- **HttpOnly:** page scripts cannot read it, so an injected script cannot steal it.
- **Secure:** sent only over HTTPS. Chrome, Edge and Firefox treat `http://localhost` as secure, so local development works. Safari does not; set `SESSION_COOKIE_SECURE=false` in `.env` only if you must test in Safari locally.
- **SameSite=Lax:** other websites cannot make the browser send it on a `POST`, which is the CSRF protection. This requires the dashboard and API to be on the **same site**: `localhost:5173` and `localhost:8000` are, and so are `app.example.test` and `api.example.test`. If deployment (SNX-25) puts them on different sites, the cookie needs `SameSite=None` plus a CSRF token, which is not built.
- **Path=/api:** the cookie is not sent with requests for the dashboard's own files.

`CORS_ORIGINS` lists the dashboard origins allowed to call the API with the cookie (default `http://localhost:5173`). Add the deployed dashboard origin there; never use `*`.

## Creating staff accounts

There is no sign-up page. A team member creates each account from the command line:

```bash
docker compose run --rm api python -m app.staff_account staff.one@example.test
```

It prompts for the password twice and never prints it. Running it again for an existing email resets the password, reactivates the account and signs it out everywhere. To deactivate an account without deleting its audit history:

```sql
UPDATE app.staff_users SET is_active = false WHERE email = 'staff.one@example.test';
```

Use synthetic emails and throwaway passwords in development. Real SolTech accounts are created only on the deployed environment, and their passwords are never shared in Jira, PRs or chat.

## Adding a protected endpoint

Put new routers on the `protected` router in `backend/app/main.py`. It requires a signed-in staff member, so an endpoint is protected by default. If a route needs the current user, for example to record who made an edit, add the `require_staff` dependency to it to receive the `StaffUser`.

## Not built in Phase 1

- Rate limiting or lockout after repeated failed sign-ins.
- Password reset by email, or changing a password from the dashboard.
- A "sign out all devices" button. A password reset does this.
- Cleanup of old session rows. Two users create few rows; add a cleanup job if that changes.
