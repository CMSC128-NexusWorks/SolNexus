from uuid import UUID

from pydantic import BaseModel


class StaffUser(BaseModel):
    """The staff summary returned by login and the session check (contract `auth.login_response`)."""

    user_id: UUID
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str
