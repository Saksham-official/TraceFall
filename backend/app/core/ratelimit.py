"""Request rate limiting, per user and per client address.

Distinct from `ingestion/ratelimit.py`, which paces our *outbound* calls to a provider's
free tier. This one limits *inbound* requests, and the shapes are different enough that
sharing an implementation would fit neither: that one enforces a minimum interval for
sub-1-per-second rates, this one counts requests in a fixed window.

**Two independent buckets, and both must pass.** A per-user limit stops one signed-in
account from monopolising the worker queue; a per-IP limit stops an unauthenticated
attacker from grinding the login endpoint without ever holding an account. Neither
substitutes for the other.

**Login is limited harder than everything else**, and by IP rather than by the email being
tried — an attacker choosing a new email each attempt would otherwise get a fresh budget
every time, which is exactly the case the limit exists for.

Redis is the store because the limit is a property of the deployment, not of one process:
two API containers behind a load balancer share one budget. If Redis is unreachable the
limiter **fails open** and says so in the log. A rate limiter that takes the API down when
its cache blinks has caused a worse outage than the one it prevents.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.orchestrator.queue import get_client

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    requests: int
    window_seconds: int

    @property
    def description(self) -> str:
        return f"{self.requests} requests per {self.window_seconds} seconds"


# Generous for an investigator clicking through a case, tight enough that a script cannot
# fill the analysis queue. Authentication is the one that matters against an attacker.
DEFAULT_PER_USER = Limit(requests=300, window_seconds=60)
DEFAULT_PER_IP = Limit(requests=600, window_seconds=60)
LOGIN_PER_IP = Limit(requests=10, window_seconds=60)

LOGIN_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/auth/refresh"})
# Health is polled by container orchestration, which must never be throttled out.
EXEMPT_PATHS = frozenset({"/api/v1/health", "/docs", "/openapi.json"})


async def hit(bucket: str, limit: Limit) -> tuple[bool, int]:
    """Count one request. Returns whether it is allowed and the seconds until reset.

    A fixed window rather than a sliding one: it is two Redis commands, it is trivially
    explainable to whoever is looking at a 429, and the burst-at-a-boundary weakness does
    not matter at these limits.
    """
    window = int(time.time()) // limit.window_seconds
    key = f"tracefall:ratelimit:{bucket}:{window}"
    try:
        client = get_client()
        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, limit.window_seconds)
        count = int((await pipeline.execute())[0])
    except Exception:  # noqa: BLE001 — availability beats enforcement here
        log.warning("rate limiter unavailable; allowing request", exc_info=True)
        return True, 0
    reset = limit.window_seconds - (int(time.time()) % limit.window_seconds)
    return count <= limit.requests, reset


def client_ip(request: Request) -> str:
    """The client address, trusting `X-Forwarded-For` only when configured to.

    Behind a load balancer the socket address is the balancer's, so every user would
    share one bucket. In front of one, an attacker sets the header themselves and gets a
    fresh bucket per request — so this is opt-in, not a default.
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        ip = client_ip(request)
        checks = [(f"ip:{ip}", DEFAULT_PER_IP)]
        if request.url.path in LOGIN_PATHS:
            checks.append((f"login:{ip}", LOGIN_PER_IP))
        # The user id is only known after authentication, which happens downstream of
        # middleware. The per-IP bucket covers the pre-auth case; the per-user bucket is
        # applied from the authenticated dependency instead.

        for bucket, limit in checks:
            allowed, reset = await hit(bucket, limit)
            if not allowed:
                return _too_many(reset, limit)
        return await call_next(request)


def _too_many(reset: int, limit: Limit) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        # The envelope every other error uses, so a client parses one shape.
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": f"Too many requests. The limit is {limit.description}.",
                "request_id": "-",
            }
        },
        headers={"Retry-After": str(reset)},
    )


async def enforce_user_limit(user_id: int) -> None:
    """Per-user limit, applied where the user is known (a route dependency).

    Raises rather than returning a response, because by this point we are inside the
    request handler and the exception handlers own the envelope.
    """
    from app.core.exceptions import RateLimited

    if not get_settings().rate_limit_enabled:
        return
    allowed, reset = await hit(f"user:{user_id}", DEFAULT_PER_USER)
    if not allowed:
        raise RateLimited(
            f"Too many requests. The limit is {DEFAULT_PER_USER.description}. "
            f"Try again in {reset} seconds."
        )
