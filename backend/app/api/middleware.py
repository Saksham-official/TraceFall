"""Request correlation and audit logging.

Reads of case resources are audited as well as mutations: in an investigation system,
who looked at which case is itself security-relevant (ADR-013).
"""

import hashlib
import re
import uuid
from collections.abc import Awaitable, Callable

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var
from app.core.security import decode_token
from app.db.models.audit import AuditLog
from app.db.session import SessionFactory

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
_CASE_UUID = re.compile(r"/cases/([0-9a-fA-F-]{36})")
# Health and auth are noise or handled separately; login failures are logged by the route.
_SKIP_PATHS = ("/api/v1/health", "/api/health", "/health", "/docs", "/openapi.json")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith(_SKIP_PATHS):
            return await call_next(request)

        is_mutation = request.method in MUTATING_METHODS
        case_match = _CASE_UUID.search(path)
        if not is_mutation and not case_match:
            return await call_next(request)

        payload_hash: str | None = None
        if is_mutation:
            # Starlette caches the body, so the route still receives it.
            body = await request.body()
            if body:
                payload_hash = hashlib.sha256(body).hexdigest()

        response = await call_next(request)

        await self._write(request, response, case_match, payload_hash)
        return response

    async def _write(
        self,
        request: Request,
        response: Response,
        case_match: re.Match[str] | None,
        payload_hash: str | None,
    ) -> None:
        actor_id = _actor_id(request)
        entry = AuditLog(
            actor_id=actor_id,
            action=f"{request.method} {response.status_code}",
            resource_type=_resource_type(request.url.path),
            resource_id=None,
            case_id=uuid.UUID(case_match.group(1)) if case_match else None,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:300] or None,
            payload_sha256=payload_hash,
        )
        async with SessionFactory() as session:
            session.add(entry)
            await session.commit()


def _actor_id(request: Request) -> int | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return int(decode_token(header.split(" ", 1)[1], expected_type="access")["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def _resource_type(path: str) -> str:
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
    return parts[0] if parts else "root"
