"""Provider health, derived from actual usage.

/health must not make network calls — it is the container healthcheck. Instead the HTTP
layer records the outcome of every real request, and health reports that. It is also more
honest: it reflects whether the provider is working for us, not whether it answers a ping.
"""

import json
from datetime import UTC, datetime

from app.orchestrator.queue import get_client

TTL_SECONDS = 900


def _key(provider: str) -> str:
    return f"tracefall:provider:{provider}"


async def record(provider: str, reachable: bool, detail: str | None = None) -> None:
    payload = {
        "reachable": reachable,
        "detail": detail,
        "at": datetime.now(UTC).isoformat(),
    }
    await get_client().set(_key(provider), json.dumps(payload), ex=TTL_SECONDS)


async def read(provider: str) -> dict[str, object] | None:
    raw = await get_client().get(_key(provider))
    return dict(json.loads(raw)) if raw else None
