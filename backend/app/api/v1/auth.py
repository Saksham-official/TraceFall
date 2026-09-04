from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Response
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.deps import CurrentUser, SessionDep
from app.core.exceptions import Unauthenticated
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models.user import RefreshToken, User
from app.orchestrator import queue
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900


async def _too_many_attempts(email: str) -> bool:
    key = f"tracefall:login:{email.lower()}"
    client = queue.get_client()
    attempts = await client.incr(key)
    if attempts == 1:
        await client.expire(key, LOCKOUT_SECONDS)
    return attempts > MAX_ATTEMPTS


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    # The response is deliberately identical for an unknown user and a wrong password;
    # distinguishing them enumerates accounts.
    invalid = Unauthenticated("Incorrect email or password")

    if await _too_many_attempts(payload.email):
        raise Unauthenticated("Too many failed attempts. Try again later.")

    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise invalid

    settings = get_settings()
    refresh, jti, expires_at = create_refresh_token(user.id)
    session.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await queue.get_client().delete(f"tracefall:login:{payload.email.lower()}")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=refresh,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(payload: RefreshRequest, session: SessionDep) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Refresh token is invalid or has expired") from exc

    stored = await session.scalar(select(RefreshToken).where(RefreshToken.jti == claims["jti"]))
    if stored is None or stored.revoked_at is not None:
        raise Unauthenticated("Refresh token has been revoked")

    user = await session.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise Unauthenticated("Account is inactive or no longer exists")

    # Rotate: the presented token is revoked and replaced.
    stored.revoked_at = datetime.now(UTC)
    new_refresh, jti, expires_at = create_refresh_token(user.id)
    session.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=new_refresh,
        expires_in=get_settings().access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(user: CurrentUser, session: SessionDep) -> Response:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
