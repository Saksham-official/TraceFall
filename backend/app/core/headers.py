"""Response security headers, including the content security policy.

The API serves JSON, not HTML, so most of these matter for one reason: a browser that is
tricked into rendering a response as a document must not then be able to run anything or
frame anything. The policy is therefore as close to "deny everything" as a JSON API can
be, rather than a copy of a front-end policy with the useful parts left in.

`Strict-Transport-Security` is sent only in production. Sending it from a development
server on plain HTTP pins the developer's browser to HTTPS for `localhost` — a
self-inflicted outage that is tedious to undo, and it protects nothing locally.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

# A JSON API needs no script, style, image or frame source of any kind. `frame-ancestors`
# is the one that actually does work here: it stops the API being framed for clickjacking,
# and unlike X-Frame-Options it cannot be overridden by a permissive ALLOW-FROM.
CSP = "; ".join(
    [
        "default-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
)

HEADERS = {
    "Content-Security-Policy": CSP,
    # Belt and braces for browsers predating frame-ancestors support.
    "X-Frame-Options": "DENY",
    # Stops a browser from sniffing a JSON error body as HTML and rendering it.
    "X-Content-Type-Options": "nosniff",
    # A request id must not leak to a third party through a referrer header.
    "Referrer-Policy": "no-referrer",
    # This API needs none of these; denying them costs nothing and shrinks the surface.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    # Case data must never sit in a shared cache, and a browser back-button must not
    # redisplay it after sign-out.
    "Cache-Control": "no-store",
}

# Two years, preloadable. Only ever sent over a real HTTPS deployment.
HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        if get_settings().environment == "production":
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response
