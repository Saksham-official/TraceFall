from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings
from app.ingestion import status
from app.orchestrator import queue

PROVIDERS = ("trongrid", "etherscan", "blockscout")

router = APIRouter(tags=["health"])


class ProviderStatus(BaseModel):
    name: str
    # None means "not used since the last restart", which is different from "down".
    reachable: bool | None = None
    last_check: str | None = None
    detail: str | None = None


class Health(BaseModel):
    status: str
    version: str
    live_mode: bool
    queue_reachable: bool
    providers: list[ProviderStatus]


@router.get("/health", response_model=Health)
async def health() -> Health:
    settings = get_settings()
    providers: list[ProviderStatus] = []
    if settings.live_mode:
        for name in PROVIDERS:
            observed = await status.read(name)
            providers.append(
                ProviderStatus(
                    name=name,
                    reachable=bool(observed["reachable"]) if observed else None,
                    last_check=str(observed["at"]) if observed else None,
                    detail=str(observed["detail"]) if observed and observed.get("detail") else None,
                )
            )
    # In fixture mode no provider is contacted, so an empty list is the honest answer.
    return Health(
        status="ok",
        version=__version__,
        live_mode=settings.live_mode,
        queue_reachable=await queue.ping(),
        providers=providers,
    )
