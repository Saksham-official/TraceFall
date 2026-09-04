"""Per-provider rate limiting, shared across workers.

Rate limits are a global resource: two workers hitting the same free tier share one
budget, so the limiter lives in Redis rather than in process.
"""

import asyncio
import time

from app.orchestrator.queue import get_client

# ponytail: fixed one-second windows, so a burst straddling a boundary can reach 2x the
# limit for one second. Swap for a Lua token bucket if a provider actually complains.
WINDOW_SECONDS = 1


async def acquire(provider: str, rate_per_second: float) -> None:
    """Block until this provider has budget for one more request."""
    limit = max(1, int(rate_per_second))
    while True:
        window = int(time.time() / WINDOW_SECONDS)
        key = f"tracefall:rl:{provider}:{window}"
        client = get_client()
        used = await client.incr(key)
        if used == 1:
            await client.expire(key, WINDOW_SECONDS * 2)
        if used <= limit:
            return
        # Wait out the remainder of this window rather than spinning.
        await asyncio.sleep(WINDOW_SECONDS - (time.time() % WINDOW_SECONDS))


async def current_usage(provider: str) -> int:
    window = int(time.time() / WINDOW_SECONDS)
    value = await get_client().get(f"tracefall:rl:{provider}:{window}")
    return int(value or 0)
