from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy import Connection

from app.auth.models import StaffUser
from app.auth.sessions import SESSION_COOKIE, find_session_user
from app.db import get_db
from app.errors import ApiError

SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def require_staff(conn: Annotated[Connection, Depends(get_db)], session_token: SessionToken = None) -> StaffUser:
    """Dependency for every non-login endpoint: the signed-in staff member, or a 401."""
    user = find_session_user(conn, session_token) if session_token else None
    if user is None:
        raise ApiError(401, "unauthorized", "Sign in required")
    return user
