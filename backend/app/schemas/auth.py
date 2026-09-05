from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    # Optional, so `POST /auth/refresh` with a body of `{}` is valid. That is what a
    # browser sends after a page reload: it kept nothing, and the token travels in the
    # httpOnly cookie instead. Requiring the field here rejected the exact client the
    # endpoint's recovery path was written for.
    refresh_token: str | None = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    organisation: str | None
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105  # OAuth scheme name, not a credential
    expires_in: int
    user: UserOut
