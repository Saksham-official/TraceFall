"""Response cache.

Correctness invariant: flushing the entire cache changes performance and nothing else.
Any cache holding the only copy of something is a bug.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.chains.base import RawResponse
from app.core.config import get_settings
from app.orchestrator.queue import get_client


def cache_key(provider: str, endpoint: str, params: dict[str, Any]) -> str:
    """Stable across parameter ordering, so equivalent requests share one entry."""
    canonical = json.dumps({"e": endpoint, "p": params}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    return f"{provider}:{digest}"


async def get(key: str) -> RawResponse | None:
    raw = await get_client().get(f"tracefall:cache:{key}")
    if raw is None:
        return None
    payload = json.loads(raw)
    return RawResponse(
        provider=payload["provider"],
        endpoint=payload["endpoint"],
        params=payload["params"],
        status=payload["status"],
        body=base64.b64decode(payload["body"]),
        retrieved_at=datetime.fromisoformat(payload["retrieved_at"]),
        from_cache=True,
        is_fixture=payload.get("is_fixture", False),
    )


async def put(key: str, response: RawResponse) -> None:
    payload = {
        "provider": response.provider,
        "endpoint": response.endpoint,
        "params": response.params,
        "status": response.status,
        "body": base64.b64encode(response.body).decode(),
        "retrieved_at": response.retrieved_at.astimezone(UTC).isoformat(),
        "is_fixture": response.is_fixture,
    }
    await get_client().set(
        f"tracefall:cache:{key}", json.dumps(payload), ex=get_settings().cache_ttl_seconds
    )
