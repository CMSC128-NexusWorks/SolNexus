from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.auth.dependencies import SessionToken, require_staff
from app.auth.models import LoginRequest, StaffUser
from app.auth.sessions import ABSOLUTE_TIMEOUT, SESSION_COOKIE, create_session, revoke_session
from app.auth.staff import authenticate
from app.core.config import settings
from app.db import Db
from app.errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentStaff = Annotated[StaffUser, Depends(require_staff)]

# Path=/api keeps the cookie off frontend requests. SameSite=Lax stops other sites from sending it on
# POSTs; it requires the dashboard and API to share a site (see docs/authentication.md).
_COOKIE_OPTIONS = {"path": "/api", "secure": settings.session_cookie_secure, "httponly": True, "samesite": "lax"}


@router.post("/login")
def login(credentials: LoginRequest, response: Response, conn: Db) -> StaffUser:
    user = authenticate(conn, credentials.email.strip(), credentials.password)
    if user is None:
        # One message for unknown email, wrong password and deactivated account.
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    token = create_session(conn, user.user_id)
    response.set_cookie(SESSION_COOKIE, token, max_age=int(ABSOLUTE_TIMEOUT.total_seconds()), **_COOKIE_OPTIONS)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, conn: Db, _: CurrentStaff, session_token: SessionToken = None) -> None:
    revoke_session(conn, session_token)
    response.delete_cookie(SESSION_COOKIE, **_COOKIE_OPTIONS)


@router.get("/session")
def current_session(user: CurrentStaff) -> StaffUser:
    """Lets the dashboard ask who is signed in, since it cannot read the HttpOnly cookie."""
    return user
