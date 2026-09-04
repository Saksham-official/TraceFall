"""Rate limiting is bucketed per (provider, method).

TronGrid meters each RPC method independently: a per-provider limiter would block calls
the provider would have allowed, and allow bursts within one method that it would not.
"""

import asyncio
import time

from app.ingestion import ratelimit


async def test_bucket_key_separates_methods() -> None:
    assert ratelimit.bucket("trongrid", "trc20") != ratelimit.bucket("trongrid", "transactions")


async def test_second_request_in_the_same_bucket_waits(clean_database: None) -> None:
    bucket = ratelimit.bucket("test-provider", "method-a")
    started = time.monotonic()
    await ratelimit.acquire(bucket, rate_per_second=5)  # 200ms interval
    await ratelimit.acquire(bucket, rate_per_second=5)
    assert time.monotonic() - started >= 0.15


async def test_different_methods_do_not_block_each_other(clean_database: None) -> None:
    started = time.monotonic()
    await asyncio.gather(
        ratelimit.acquire(ratelimit.bucket("test-provider", "m1"), 1),
        ratelimit.acquire(ratelimit.bucket("test-provider", "m2"), 1),
        ratelimit.acquire(ratelimit.bucket("test-provider", "m3"), 1),
    )
    assert time.monotonic() - started < 0.5, "independent buckets must not serialise"


async def test_sub_one_per_second_rates_are_supported(clean_database: None) -> None:
    """The measured TronGrid rate is 0.5/s, so a per-second counter cannot express it."""
    bucket = ratelimit.bucket("test-provider", "slow")
    await ratelimit.acquire(bucket, rate_per_second=0.5)
    assert await ratelimit.is_held(bucket)
