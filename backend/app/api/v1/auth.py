from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, Response
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

# SECURITY.md §9: the refresh token is issued as an httpOnly cookie so a browser can survive
# a page reload without ever putting a token somewhere script — and therefore XSS — can read.
REFRESH_COOKIE = "tracefall_refresh"  # noqa: S105  # cookie name, not a credential
# Scoped to the auth routes: no other endpoint needs the refresh token, so no other endpoint
# is sent it, and it never rides along on the many case/analysis requests.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _write_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    """Set (or, with an empty token and ``max_age=0``, clear) the refresh cookie.

    One writer for both, because a cookie is only replaced or cleared when name, path and
    flags match exactly. ``secure`` is environment-driven and never hardcoded: a Secure
    cookie is dropped by the browser over plain HTTP, which would break development on
    http://localhost, while omitting it in production would expose the token to a
    downgraded request.
    """
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=get_settings().environment == "production",
        path=REFRESH_COOKIE_PATH,
    )


async def _too_many_attempts(email: str) -> bool:
    key = f"tracefall:login:{email.lower()}"
    client = queue.get_client()
    attempts = await client.incr(key)
    if attempts == 1:
        await client.expire(key, LOCKOUT_SECONDS)
    return attempts > MAX_ATTEMPTS


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, session: SessionDep) -> TokenResponse:
    """Authenticate and open a session.

    The refresh token is issued twice: in the response body, for non-browser clients that
    keep no cookie jar, and as an httpOnly cookie for browsers. A browser may therefore
    discard the body token entirely and still recover the session after a reload by calling
    `POST /auth/refresh` with no body — see that endpoint.
    """
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

    _write_refresh_cookie(response, refresh, settings.refresh_token_days * 86_400)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=refresh,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    response: Response,
    session: SessionDep,
    cookie_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    payload: RefreshRequest | None = None,
) -> TokenResponse:
    """Rotate the refresh token and issue a new access token.

    **This is also the session-recovery endpoint.** A browser that kept nothing across a
    page reload calls `POST /auth/refresh` with an empty body: the refresh token is read
    from the httpOnly cookie set at login, and the response is a full `TokenResponse` — a
    working access token, a rotated refresh token, and the user.

    The token is taken from the cookie when one is present and from the request body
    otherwise, so existing non-browser clients are unaffected. Cookie-first means a browser
    always converges on the newest token even if its in-memory copy has fallen behind.
    """
    token = cookie_token or (payload.refresh_token if payload else None)
    if token is None:
        raise Unauthenticated("No refresh token was supplied")

    try:
        claims = decode_token(token, expected_type="refresh")
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

    settings = get_settings()
    _write_refresh_cookie(response, new_refresh, settings.refresh_token_days * 86_400)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=new_refresh,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(user: CurrentUser, session: SessionDep) -> Response:
    """Revoke every refresh token held by the user and clear the browser cookie.

    Server-side revocation is what actually ends the session; clearing the cookie stops the
    browser from replaying a token it can no longer use.
    """
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()

    response = Response(status_code=204)
    _write_refresh_cookie(response, "", 0)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
