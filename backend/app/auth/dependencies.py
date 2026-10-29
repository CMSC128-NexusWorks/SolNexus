from typing import Annotated

from fastapi import Cookie

from app.auth.models import StaffUser
from app.auth.sessions import SESSION_COOKIE, find_session_user
from app.db import engine
from app.errors import ApiError

SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def require_staff(session_token: SessionToken = None) -> StaffUser:
    """Dependency for every non-login endpoint: the signed-in staff member, or a 401."""
    if not session_token:
        raise ApiError(401, "unauthorized", "Sign in required")
    # Its own short transaction, not the request's Db: the idle-window refresh must commit even when
    # the route later raises (a 404 or 409 is still activity), and the request rollback would undo it.
    with engine.begin() as conn:
        user = find_session_user(conn, session_token)
    if user is None:
        raise ApiError(401, "unauthorized", "Sign in required")
    return user
