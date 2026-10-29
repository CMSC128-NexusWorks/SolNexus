import re
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import Connection, text

from app.auth.models import StaffUser
from app.auth.sessions import revoke_user_sessions

MIN_PASSWORD_LENGTH = 12
# Same pattern as the staff_users_email_check constraint (migration 0002). Checking first turns a bad
# address into a clear ValueError instead of an IntegrityError traceback that prints the INSERT.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+")

_hasher = PasswordHasher()
# Checked when the email is unknown, so a missing account takes as long as a wrong password.
_UNKNOWN_USER_HASH = _hasher.hash("solnexus-unknown-user")


def authenticate(conn: Connection, email: str, password: str) -> StaffUser | None:
    """Return the staff member if the credentials match an active account, otherwise None."""
    row = conn.execute(
        text("SELECT user_id, email, password_hash, is_active FROM app.staff_users WHERE email = :email"),
        {"email": email},
    ).one_or_none()
    try:
        matches = _hasher.verify(row.password_hash if row else _UNKNOWN_USER_HASH, password)
    except (VerificationError, InvalidHashError):
        # InvalidHashError covers the unusable placeholder hashes in backend/fixtures/dev_seed.sql.
        matches = False
    if not matches or row is None or not row.is_active:
        return None
    return StaffUser(user_id=row.user_id, email=row.email)


def set_staff_password(conn: Connection, email: str, password: str) -> UUID:
    """Create a staff account, or reset its password and reactivate it. Signs out its existing sessions."""
    if not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Email must be a full address, like name@example.test")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    user_id = conn.execute(
        text(
            """
            INSERT INTO app.staff_users (email, password_hash) VALUES (:email, :password_hash)
            ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_active = true
            RETURNING user_id
            """
        ),
        {"email": email, "password_hash": _hasher.hash(password)},
    ).scalar_one()
    revoke_user_sessions(conn, user_id)
    return user_id
