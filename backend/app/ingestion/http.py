"""HTTP transport for provider calls.

Retry with exponential backoff and jitter, a hard timeout, and rate limiting before
every request (NFR-05). Returns the raw body untouched — parsing happens later, so a
provider changing its response shape produces a typed parse error rather than losing
the evidence.
"""

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any

import httpx

from app.chains.base import (
    ProviderRateLimited,
    ProviderUnavailable,
    RawResponse,
    redact_request_params,
)
from app.core.config import get_settings
from app.ingestion import ratelimit, status

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 16.0

# TronGrid sends no Retry-After and no rate-limit headers — the suspension duration
# appears only in the prose body, measured at ~5.5s. A 1/2/4s backoff spends every retry
# inside that window and then fails over for no reason, so throttling gets its own floor.
THROTTLE_FLOOR_SECONDS = 6.0

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=get_settings().http_timeout_seconds,
            headers={"User-Agent": "TraceFall/0.1 (blockchain investigation research)"},
            follow_redirects=True,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _backoff(attempt: int, retry_after: float | None, throttled: bool = False) -> float:
    if retry_after is not None:
        return min(retry_after, MAX_BACKOFF_SECONDS)
    if throttled:
        return min(THROTTLE_FLOOR_SECONDS * (attempt + 1), MAX_BACKOFF_SECONDS)
    # Jitter keeps concurrent workers from retrying in lockstep.
    jitter = 0.5 + random.random() / 2  # noqa: S311  # jitter, not a security decision
    return float(min(BASE_BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS) * jitter)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


async def fetch(
    provider: str,
    url: str,
    params: dict[str, Any],
    rate_per_second: float,
    headers: dict[str, str] | None = None,
    method: str = "default",
) -> RawResponse:
    """One provider request, with rate limiting and retries.

    Raises ProviderRateLimited or ProviderUnavailable once retries are exhausted; the
    ingestion service turns those into a partial result rather than letting them escape.
    """
    settings = get_settings()
    client = get_http_client()
    last_error = "unknown"

    for attempt in range(settings.http_max_retries + 1):
        await ratelimit.acquire(ratelimit.bucket(provider, method), rate_per_second)
        try:
            response = await client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("%s request failed (attempt %d): %s", provider, attempt + 1, last_error)
            if attempt < settings.http_max_retries:
                await asyncio.sleep(_backoff(attempt, None))
                continue
            await status.record(provider, False, last_error)
            raise ProviderUnavailable(f"{provider} unreachable: {last_error}") from exc

        if response.status_code in RETRYABLE_STATUS:
            wait = _backoff(attempt, _retry_after(response), throttled=response.status_code == 429)
            last_error = f"HTTP {response.status_code}"
            log.warning(
                "%s returned %d (attempt %d), backing off %.1fs",
                provider,
                response.status_code,
                attempt + 1,
                wait,
            )
            if attempt < settings.http_max_retries:
                await asyncio.sleep(wait)
                continue
            await status.record(provider, False, last_error)
            if response.status_code == 429:
                raise ProviderRateLimited(
                    f"{provider} rate limited after {attempt + 1} attempts",
                    retry_after=_retry_after(response),
                )
            raise ProviderUnavailable(f"{provider} returned {response.status_code}")

        if response.status_code >= 400:
            # A 4xx is the provider's considered answer, not a transient fault.
            await status.record(provider, False, f"HTTP {response.status_code}")
            raise ProviderUnavailable(f"{provider} returned {response.status_code}")

        await status.record(provider, True)
        return RawResponse(
            provider=provider,
            endpoint=url,
            params=redact_request_params(params),
            status=response.status_code,
            body=response.content,
            retrieved_at=datetime.now(UTC),
        )

    raise ProviderUnavailable(f"{provider} failed: {last_error}")
