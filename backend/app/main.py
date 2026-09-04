from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="TraceFall API",
    version=__version__,
    # Docs are a development convenience, not a production surface.
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProviderStatus(BaseModel):
    name: str
    reachable: bool


class Health(BaseModel):
    status: str
    version: str
    live_mode: bool
    providers: list[ProviderStatus]


@app.get("/api/v1/health", response_model=Health)
def health() -> Health:
    # providers stays empty until Phase 3 wires the chain adapters.
    return Health(
        status="ok",
        version=__version__,
        live_mode=settings.live_mode,
        providers=[],
    )
