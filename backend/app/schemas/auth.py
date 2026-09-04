from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


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
