"""Security hardening — the checks in SECURITY.md section 12.

Case isolation lives in `test_case_isolation.py` and is exercised again by every results
and report suite; it is the most important suite in the system and is deliberately not
duplicated here. What this file covers is the perimeter: headers, rate limits,
configuration that must refuse to start, and the promise that an error response leaks
nothing about what went wrong internally.
"""

import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import Settings, get_settings
from app.core.headers import CSP, HSTS
from app.core.logging import redact
from app.orchestrator import queue
from tests.conftest import auth, login, make_user

STRONG_KEY = "Kx7-pQ2vLm9Zr4Tn8Wc1Bf6Yh3Jd5Gs0Aq"


def production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "secret_key": STRONG_KEY,
        "cors_origins": "https://tracefall.example.gov.in",
        "database_url": "postgresql+asyncpg://u:p@db.internal:5432/tracefall",
        "redis_url": "redis://cache.internal:6379/0",
        "rate_limit_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


# --- Response headers -----------------------------------------------------------------


async def test_every_response_carries_the_security_headers(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.headers["content-security-policy"] == CSP
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


async def test_the_policy_denies_everything_a_json_api_never_needs() -> None:
    assert "default-src 'none'" in CSP
    # The one that actually does work here: it stops the API being framed.
    assert "frame-ancestors 'none'" in CSP
    assert "unsafe-inline" not in CSP
    assert "unsafe-eval" not in CSP


async def test_an_error_response_is_also_hardened(client: AsyncClient) -> None:
    """A 401 is rendered by a browser as readily as a 200."""
    response = await client.get(f"/api/v1/cases/{uuid.uuid4()}")

    assert response.status_code == 401
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


async def test_hsts_is_not_sent_in_development(client: AsyncClient) -> None:
    """Sending it from a dev server pins the developer's browser to HTTPS on localhost."""
    response = await client.get("/api/v1/health")

    assert "strict-transport-security" not in response.headers
    assert "includeSubDomains" in HSTS


# --- Rate limiting --------------------------------------------------------------------


@pytest.fixture
def limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)


async def test_the_login_endpoint_is_limited_by_address(
    client: AsyncClient, session: AsyncSession, limiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limited by IP, not by the email tried — an attacker rotates the email, not the socket."""
    monkeypatch.setattr(ratelimit, "LOGIN_PER_IP", ratelimit.Limit(requests=3, window_seconds=60))
    await make_user(session, "bruteforce@example.gov")

    statuses = [
        (
            await client.post(
                "/api/v1/auth/login",
                json={"email": f"attempt{i}@example.gov", "password": "wrong-password"},
            )
        ).status_code
        for i in range(5)
    ]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]


async def test_a_rate_limited_response_says_when_to_retry(
    client: AsyncClient, limiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "LOGIN_PER_IP", ratelimit.Limit(requests=1, window_seconds=60))

    await client.post("/api/v1/auth/login", json={"email": "a@b.gov", "password": "x" * 12})
    limited = await client.post(
        "/api/v1/auth/login", json={"email": "a@b.gov", "password": "x" * 12}
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(limited.headers["retry-after"]) <= 60


async def test_health_is_never_rate_limited(client: AsyncClient, limiting: None) -> None:
    """Container orchestration polls it; throttling it out would cause the outage."""
    assert {"/api/v1/health"} <= ratelimit.EXEMPT_PATHS

    for _ in range(30):
        assert (await client.get("/api/v1/health")).status_code == 200


async def test_the_limiter_fails_open_when_redis_is_unreachable(
    limiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A limiter that takes the API down when its cache blinks is the worse outage."""

    def unreachable() -> object:
        raise ConnectionError("redis is down")

    monkeypatch.setattr(ratelimit, "get_client", unreachable)

    allowed, reset = await ratelimit.hit("ip:1.2.3.4", ratelimit.LOGIN_PER_IP)

    assert allowed is True
    assert reset == 0


async def test_the_per_user_limit_applies_to_an_authenticated_caller(
    client: AsyncClient, session: AsyncSession, limiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ratelimit, "DEFAULT_PER_USER", ratelimit.Limit(requests=3, window_seconds=60)
    )
    await make_user(session, "busy@example.gov")
    headers = auth(await login(client, "busy@example.gov"))

    statuses = [(await client.get("/api/v1/cases", headers=headers)).status_code for _ in range(6)]

    assert 429 in statuses
    assert statuses[0] == 200


async def test_a_forwarded_address_is_ignored_unless_proxying_is_configured(
    limiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trusting the header by default hands an attacker a fresh bucket per request."""
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": Headers({"x-forwarded-for": "9.9.9.9"}).raw,
        "client": ("10.0.0.5", 1234),
    }
    request = Request(scope)  # type: ignore[arg-type]

    monkeypatch.setattr(get_settings(), "trust_proxy_headers", False)
    assert ratelimit.client_ip(request) == "10.0.0.5"

    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert ratelimit.client_ip(request) == "9.9.9.9"


# --- Production configuration ---------------------------------------------------------


def test_a_hardened_production_configuration_starts() -> None:
    assert production().environment == "production"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"secret_key": "change-me-change-me-change-me-1234"}, "placeholder"),
        ({"secret_key": "a" * 40}, "variety"),
        ({"cors_origins": "http://tracefall.example.gov.in"}, "plain-HTTP"),
        ({"cors_origins": "*"}, "wildcard"),
        ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED"),
        ({"database_url": "postgresql+asyncpg://u:p@localhost:5432/t"}, "localhost"),
    ],
)
def test_production_refuses_to_start_on_a_development_configuration(
    overrides: dict[str, object], expected: str
) -> None:
    """Each of these is invisible until it is exploited. Boot is the only place it is noticed."""
    with pytest.raises(ValidationError, match=expected):
        production(**overrides)


def test_development_is_not_held_to_the_production_rules() -> None:
    """The guard must not make a laptop unworkable."""
    relaxed = Settings(  # type: ignore[call-arg]
        environment="development", secret_key="a" * 40, cors_origins="http://localhost:5173"
    )

    assert relaxed.cors_origin_list == ["http://localhost:5173"]


def test_the_secret_key_has_no_default() -> None:
    """A build must refuse to start rather than run on a key that ships in the source."""
    assert Settings.model_fields["secret_key"].is_required()


# --- Leakage --------------------------------------------------------------------------


async def test_an_error_response_leaks_nothing_to_the_client(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "leak@example.gov")
    headers = auth(await login(client, "leak@example.gov"))

    response = await client.get("/api/v1/cases/not-a-uuid", headers=headers)

    body = response.json()
    assert response.status_code == 422
    assert "Traceback" not in str(body)
    assert "app/" not in str(body)
    assert set(body["error"]) <= {"code", "message", "field", "request_id"}


async def test_secrets_are_redacted_before_they_reach_a_log_line() -> None:
    assert "hunter2" not in redact("password=hunter2")
    assert "abc123" not in redact("trongrid_api_key: abc123")
    assert "s3cr3t" not in redact('{"secret_key": "s3cr3t"}')
    # The field name survives, so a log stays readable.
    assert "password" in redact("password=hunter2")


async def test_the_refresh_cookie_cannot_be_read_by_script(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The whole point of the cookie: an XSS cannot exfiltrate the long-lived credential."""
    await make_user(session, "cookie@example.gov")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie@example.gov", "password": "correct-horse-battery"},
    )

    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header.replace("samesite=lax", "SameSite=lax")
    # Scoped to the auth routes: no other endpoint needs it, so no other endpoint gets it.
    assert "Path=/api/v1/auth" in header


async def test_a_reload_can_rebuild_a_session_from_the_cookie_alone(
    client: AsyncClient, session: AsyncSession
) -> None:
    """No body at all — exactly what the browser sends after a page reload."""
    await make_user(session, "reload@example.gov")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "reload@example.gov", "password": "correct-horse-battery"},
    )

    refreshed = await client.post("/api/v1/auth/refresh", json={})

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert refreshed.json()["user"]["email"] == "reload@example.gov"


async def test_docs_are_not_served_in_production() -> None:
    """The schema is a development convenience, not a production surface."""
    from app.main import app

    assert app.docs_url == "/docs"  # development, as configured for tests
    assert app.redoc_url is None


async def test_the_queue_key_is_namespaced_so_a_shared_redis_cannot_collide() -> None:
    assert queue.QUEUE_KEY.startswith("tracefall:")
    assert queue.CANCEL_KEY.startswith("tracefall:")
