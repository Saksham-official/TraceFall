from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings
from app.orchestrator import queue

router = APIRouter(tags=["health"])


class ProviderStatus(BaseModel):
    name: str
    reachable: bool


class Health(BaseModel):
    status: str
    version: str
    live_mode: bool
    queue_reachable: bool
    providers: list[ProviderStatus]


@router.get("/health", response_model=Health)
async def health() -> Health:
    # providers stays empty until Phase 3 wires the chain adapters.
    return Health(
        status="ok",
        version=__version__,
        live_mode=get_settings().live_mode,
        queue_reachable=await queue.ping(),
        providers=[],
    )
