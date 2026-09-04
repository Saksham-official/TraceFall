from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.user import RefreshToken
from tests.conftest import auth, login, make_user


async def test_login_returns_tokens(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "investigator@example.gov")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "investigator@example.gov", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "investigator@example.gov"
    assert "password_hash" not in body["user"]


async def test_unknown_user_and_wrong_password_are_indistinguishable(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Distinguishing them enumerates accounts."""
    await make_user(session, "real@example.gov")
    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": "real@example.gov", "password": "not-the-password"}
    )
    unknown_user = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.gov", "password": "not-the-password"}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


async def test_inactive_user_cannot_log_in(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session, "retired@example.gov")
    user.is_active = False
    await session.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "retired@example.gov", "password": "correct-horse-battery"},
    )
    assert response.status_code == 401


async def test_repeated_failures_are_throttled(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "target@example.gov")
    payload = {"email": "target@example.gov", "password": "wrong"}
    for _ in range(5):
        await client.post("/api/v1/auth/login", json=payload)
    blocked = await client.post("/api/v1/auth/login", json=payload)
    assert blocked.status_code == 401
    assert "Too many" in blocked.json()["error"]["message"]


async def test_me_requires_a_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_expired_access_token_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session, "expired@example.gov")
    settings = get_settings()
    stale = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert (await client.get("/api/v1/auth/me", headers=auth(stale))).status_code == 401


async def test_refresh_token_cannot_be_used_as_an_access_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "swap@example.gov")
    tokens = await client.post(
        "/api/v1/auth/login",
        json={"email": "swap@example.gov", "password": "correct-horse-battery"},
    )
    refresh = tokens.json()["refresh_token"]
    assert (await client.get("/api/v1/auth/me", headers=auth(refresh))).status_code == 401


async def test_refresh_rotates_and_revokes_the_old_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "rotate@example.gov")
    first = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "rotate@example.gov", "password": "correct-horse-battery"},
        )
    ).json()

    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]

    # The cookie now holds the rotated token and takes precedence over the body, so it is
    # dropped here to replay the spent token itself rather than the client's newest one.
    client.cookies.clear()
    reused = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert reused.status_code == 401


async def test_logout_revokes_every_refresh_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session, "out@example.gov")
    tokens = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "out@example.gov", "password": "correct-horse-battery"},
        )
    ).json()

    assert (
        await client.post("/api/v1/auth/logout", headers=auth(tokens["access_token"]))
    ).status_code == 204

    retry = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert retry.status_code == 401

    stored = await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
    assert all(t.revoked_at is not None for t in stored.all())


async def test_password_is_never_returned_or_stored_in_clear(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session, "hash@example.gov")
    assert "correct-horse-battery" not in user.password_hash
    assert user.password_hash.startswith("$argon2")
    token = await login(client, "hash@example.gov")
    body = (await client.get("/api/v1/auth/me", headers=auth(token))).json()
    assert "password" not in str(body).lower()


# --- Refresh cookie (SECURITY.md §9) -------------------------------------------------


def refresh_cookie_header(response: Response) -> str:
    """The raw Set-Cookie line for the refresh cookie — flags are not exposed on the jar."""
    headers = response.headers.get_list("set-cookie")
    matches = [h for h in headers if h.startswith("tracefall_refresh=")]
    assert len(matches) == 1, headers
    return matches[0]


async def test_login_sets_an_httponly_refresh_cookie(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "cookie@example.gov")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie@example.gov", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200

    header = refresh_cookie_header(response)
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/api/v1/auth" in header
    # The body still carries the same token, for clients that keep no cookie jar.
    assert client.cookies["tracefall_refresh"] == response.json()["refresh_token"]


async def test_refresh_works_from_the_cookie_alone(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The reload case: the browser kept nothing but the httpOnly cookie."""
    await make_user(session, "reload@example.gov")
    first = await client.post(
        "/api/v1/auth/login",
        json={"email": "reload@example.gov", "password": "correct-horse-battery"},
    )

    recovered = await client.post("/api/v1/auth/refresh")
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["user"]["email"] == "reload@example.gov"
    assert body["refresh_token"] != first.json()["refresh_token"]

    # The recovered access token actually works.
    me = await client.get("/api/v1/auth/me", headers=auth(body["access_token"]))
    assert me.status_code == 200


async def test_refresh_still_accepts_a_body_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Backward compatibility: a client with no cookie jar sends the token in the body."""
    await make_user(session, "apiclient@example.gov")
    tokens = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "apiclient@example.gov", "password": "correct-horse-battery"},
        )
    ).json()
    client.cookies.clear()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]


async def test_refresh_without_a_token_anywhere_is_rejected(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_clears_the_cookie_and_revokes_the_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "bye@example.gov")
    tokens = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "bye@example.gov", "password": "correct-horse-battery"},
        )
    ).json()

    logout = await client.post("/api/v1/auth/logout", headers=auth(tokens["access_token"]))
    assert logout.status_code == 204
    assert "Max-Age=0" in refresh_cookie_header(logout)
    assert "tracefall_refresh" not in client.cookies

    # Cleared in the browser and revoked on the server: neither route back in works.
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


async def test_cookie_is_not_secure_in_development(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Secure would be dropped by the browser over plain HTTP, breaking localhost."""
    assert get_settings().environment == "development"
    await make_user(session, "dev@example.gov")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev@example.gov", "password": "correct-horse-battery"},
    )
    assert "Secure" not in refresh_cookie_header(response)


async def test_cookie_is_secure_in_production(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_user(session, "prod@example.gov")
    production = get_settings().model_copy(update={"environment": "production"})
    monkeypatch.setattr("app.api.v1.auth.get_settings", lambda: production)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "prod@example.gov", "password": "correct-horse-battery"},
    )
    assert "Secure" in refresh_cookie_header(response)
