import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.middleware import AuditMiddleware, RequestContextMiddleware
from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.exceptions import TraceFallError, ValidationFailed
from app.core.headers import SecurityHeadersMiddleware
from app.core.logging import configure_logging
from app.core.ratelimit import RateLimitMiddleware
from app.db.seed import seed_demo_data

configure_logging()
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        await seed_demo_data()
    except Exception as e:
        log.warning("Auto-seed error on startup: %s", e)
    yield


app = FastAPI(
    title="TraceFall API",
    version=__version__,
    # Docs are a development convenience, not a production surface.
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware runs in reverse registration order, so this list reads bottom-up: security
# headers wrap everything (a rate-limit rejection needs them too), then the correlation id
# is set before anything that logs, then the rate limiter rejects before the request
# reaches a handler, and auditing sits closest to the route.
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/api/health", tags=["health"], summary="Lightweight health ping")
@app.get("/health", tags=["health"], summary="Lightweight health ping")
async def ping() -> dict[str, str]:
    """Lightweight ping endpoint for uptime monitors and container keep-alive."""
    return {"status": "ok"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


@app.exception_handler(TraceFallError)
async def handle_known(request: Request, exc: TraceFallError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.envelope(_request_id(request)))


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query"))
    error = ValidationFailed(first.get("msg", "Request validation failed"), field=field or None)
    return JSONResponse(status_code=422, content=error.envelope(_request_id(request)))


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Detail goes to the log, never to the client.
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=TraceFallError().envelope(_request_id(request)))
