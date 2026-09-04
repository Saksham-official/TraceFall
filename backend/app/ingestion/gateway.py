"""Single entry point for every provider request.

Routing: fixture mode short-circuits to the committed snapshot; live mode checks the
cache, then goes to the network. Concurrent requests for the same key are coalesced —
during a trace, hot addresses are requested constantly, and this is worth more than any
other rate-limit optimisation.

Depends only on http, cache and fixtures, so chain adapters can import it without a cycle.
"""

import asyncio
import logging
from typing import Any

from app.chains.base import RawResponse
from app.core.config import get_settings
from app.ingestion import cache, fixtures, http

log = logging.getLogger(__name__)

_inflight: dict[str, asyncio.Task[RawResponse]] = {}


async def request(
    provider: str,
    url: str,
    params: dict[str, Any],
    rate_per_second: float,
    headers: dict[str, str] | None = None,
    method: str = "default",
) -> RawResponse:
    if not get_settings().live_mode:
        # Fixture mode is offline by construction: no cache, no network.
        return fixtures.load(provider, fixtures.fixture_key(provider, url, params))

    key = cache.cache_key(provider, url, params)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    existing = _inflight.get(key)
    if existing is not None:
        return await asyncio.shield(existing)

    task = asyncio.create_task(
        _fetch_and_cache(provider, url, params, rate_per_second, headers, key, method)
    )
    _inflight[key] = task
    try:
        return await task
    finally:
        _inflight.pop(key, None)


async def _fetch_and_cache(
    provider: str,
    url: str,
    params: dict[str, Any],
    rate_per_second: float,
    headers: dict[str, str] | None,
    key: str,
    method: str,
) -> RawResponse:
    response = await http.fetch(provider, url, params, rate_per_second, headers, method)
    await cache.put(key, response)
    return response


def fixture_key(provider: str, url: str, params: dict[str, Any]) -> str:
    """Exposed so the capture script writes fixtures under the key the gateway reads."""
    return fixtures.fixture_key(provider, url, params)
