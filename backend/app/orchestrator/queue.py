"""Redis-backed job queue.

A Redis list is enough: LPUSH to enqueue, BRPOP to consume, one key for cancellation.
A task framework would add a dependency and an operational surface for behaviour this
already provides.
"""

import uuid

import redis.asyncio as redis

from app.core.config import get_settings

QUEUE_KEY = "tracefall:analysis:queue"
CANCEL_KEY = "tracefall:analysis:cancelled"

_client: redis.Redis | None = None


# The worker blocks on BRPOP for POLL_TIMEOUT seconds at a time, so the socket must
# tolerate a read that long. redis-py's default is no timeout at all, which sounds safer
# and is not: a connection silently dropped by the network never returns, and the health
# check below is what notices. `retry_on_timeout` covers the transient case rather than
# letting one blip end the worker process.
SOCKET_TIMEOUT_SECONDS = 30
HEALTH_CHECK_SECONDS = 30


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=10,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_SECONDS,
            retry_on_timeout=True,
        )
    return _client


async def enqueue(run_id: uuid.UUID) -> None:
    await get_client().lpush(QUEUE_KEY, str(run_id))


async def dequeue(timeout: int = 5) -> str | None:
    result = await get_client().brpop([QUEUE_KEY], timeout=timeout)
    # decode_responses=True, so the payload is already str.
    return str(result[1]) if result else None


async def depth() -> int:
    return int(await get_client().llen(QUEUE_KEY))


async def request_cancel(run_id: uuid.UUID) -> None:
    await get_client().sadd(CANCEL_KEY, str(run_id))


async def is_cancelled(run_id: uuid.UUID | str) -> bool:
    return bool(await get_client().sismember(CANCEL_KEY, str(run_id)))


async def ping() -> bool:
    try:
        return bool(await get_client().ping())
    except redis.RedisError:
        return False
