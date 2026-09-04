"""Per-bucket rate limiting, shared across workers.

Rate limits are a global resource: two workers hitting the same free tier share one
budget, so the limiter lives in Redis rather than in process.

**Buckets are per (provider, method), not per provider.** TronGrid meters each RPC method
independently — three methods called concurrently all succeed while any one of them alone
is capped. A per-provider limiter is therefore both wrong and needlessly slow.

Sub-1-per-second rates are the normal case here (measured TronGrid: 0.5/s per method), so
this enforces a minimum interval rather than a per-second count.
"""

import asyncio
import time

from app.orchestrator.queue import get_client

# Redis SET NX PX is the gate: at most one holder per interval, across all workers.
POLL_SECONDS = 0.05
MAX_WAIT_SECONDS = 60.0


def bucket(provider: str, method: str) -> str:
    return f"{provider}:{method}"


async def acquire(bucket_key: str, rate_per_second: float) -> None:
    """Block until this bucket may issue one more request."""
    interval_ms = max(1, int(1000 / max(rate_per_second, 0.001)))
    key = f"tracefall:rl:{bucket_key}"
    client = get_client()
    deadline = time.monotonic() + MAX_WAIT_SECONDS

    while True:
        if await client.set(key, "1", nx=True, px=interval_ms):
            return
        if time.monotonic() > deadline:
            # Never block an analysis forever; the caller's retry loop takes over.
            return
        ttl_ms = await client.pttl(key)
        await asyncio.sleep(max(POLL_SECONDS, (ttl_ms or 0) / 1000))


async def is_held(bucket_key: str) -> bool:
    return bool(await get_client().exists(f"tracefall:rl:{bucket_key}"))
