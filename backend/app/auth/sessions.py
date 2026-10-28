import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import Connection, text

from app.auth.models import StaffUser

SESSION_COOKIE = "solnexus_session"
IDLE_TIMEOUT = timedelta(hours=8)
ABSOLUTE_TIMEOUT = timedelta(days=7)
# Activity refreshes last_seen_at at most this often, so ordinary reads don't write on every request.
TOUCH_INTERVAL = timedelta(minutes=5)


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def create_session(conn: Connection, user_id: UUID) -> str:
    """Start a session and return its token. Only the token's hash is stored."""
    token = secrets.token_urlsafe(32)
    conn.execute(
        text(
            "INSERT INTO app.staff_sessions (user_id, token_sha256, expires_at) "
            "VALUES (:user_id, :digest, now() + :lifetime)"
        ),
        {"user_id": user_id, "digest": _digest(token), "lifetime": ABSOLUTE_TIMEOUT},
    )
    return token


def find_session_user(conn: Connection, token: str) -> StaffUser | None:
    """Return the staff member for a live session, extending its idle window; None if it isn't live."""
    row = conn.execute(
        text(
            """
            SELECT s.session_id, u.user_id, u.email, s.last_seen_at < now() - :touch AS needs_touch
            FROM app.staff_sessions s
            JOIN app.staff_users u ON u.user_id = s.user_id
            WHERE s.token_sha256 = :digest
              AND s.revoked_at IS NULL
              AND s.expires_at > now()
              AND s.last_seen_at > now() - :idle
              AND u.is_active
            """
        ),
        {"digest": _digest(token), "touch": TOUCH_INTERVAL, "idle": IDLE_TIMEOUT},
    ).one_or_none()
    if row is None:
        return None
    if row.needs_touch:
        conn.execute(
            text("UPDATE app.staff_sessions SET last_seen_at = now() WHERE session_id = :session_id"),
            {"session_id": row.session_id},
        )
    return StaffUser(user_id=row.user_id, email=row.email)


def revoke_session(conn: Connection, token: str) -> None:
    conn.execute(
        text("UPDATE app.staff_sessions SET revoked_at = now() WHERE token_sha256 = :digest AND revoked_at IS NULL"),
        {"digest": _digest(token)},
    )


def revoke_user_sessions(conn: Connection, user_id: UUID) -> None:
    conn.execute(
        text("UPDATE app.staff_sessions SET revoked_at = now() WHERE user_id = :user_id AND revoked_at IS NULL"),
        {"user_id": user_id},
    )
