"""Password hashing and JWT issuance.

Argon2id for passwords (memory-hard). Short-lived access tokens plus rotating refresh
tokens held server-side so a session can actually be revoked.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        # A corrupt or legacy hash must fail authentication, not raise a 500.
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "jti": uuid.uuid4().hex,
        }
    )


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The jti is stored so the token can be revoked."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.refresh_token_days)
    jti = uuid.uuid4().hex
    token = _encode(
        {"sub": str(user_id), "type": "refresh", "iat": now, "exp": expires_at, "jti": jti}
    )
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on an invalid, expired, or wrong-type token."""
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload
