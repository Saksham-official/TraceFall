"""Committed fixture cache — real provider responses, frozen (ADR-009).

This is not mock data. It gives a demo that runs with no network and no rate limits, and
tests that are deterministic over real-world messiness. Fixtures always surface with
`is_fixture=True` so the UI can show its "cached snapshot" banner (NFR-15).

**Stored gzipped**, because they are large and enormously repetitive. One demo trace runs
through service addresses with twenty thousand transfers between them; uncompressed that
is a hundred megabytes of committed JSON, and gzip takes roughly a tenth of it. The
decompression cost is invisible next to the parsing that follows.
"""

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.chains.base import RawResponse
from app.core.config import get_settings
from app.core.paths import resolve

# Params derived from wall-clock time or credentials would make a fixture key unmatchable
# on replay: a window computed as "last 90 days" differs every run. They are excluded from
# the fixture key but still sent to the provider, so live behaviour is unchanged.
#
# The consequence is deliberate and documented: fixture mode serves one captured snapshot
# per address regardless of the requested window. Window filtering happens during
# normalization, which is where it belongs.
VOLATILE_PARAMS = frozenset(
    {"min_timestamp", "max_timestamp", "startblock", "endblock", "apikey", "timestamp"}
)


class FixtureMissing(RuntimeError):
    """Raised in fixture mode when a request has no recorded response.

    The message names the capture command, because the alternative — silently returning
    empty — would look like an address with no activity.
    """


def fixture_root() -> Path:
    """Where committed fixtures live.

    Searched rather than derived from `__file__`, so the same setting works from a source
    checkout and from an image where the package is installed elsewhere. Capture writes
    here too, so a directory that does not exist yet is created rather than rejected.
    """
    configured = Path(get_settings().fixture_path)
    if configured.is_absolute():
        return configured
    try:
        return resolve(str(configured), setting="FIXTURE_PATH")
    except FileNotFoundError:
        # Capture runs before any fixture exists.
        return Path.cwd() / configured


def fixture_key(provider: str, endpoint: str, params: dict[str, Any]) -> str:
    """Stable across runs: excludes time-derived and credential parameters."""
    stable = {k: v for k, v in params.items() if k not in VOLATILE_PARAMS}
    canonical = json.dumps({"e": endpoint, "p": stable}, sort_keys=True, separators=(",", ":"))
    return f"{provider}:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def _path(provider: str, key: str) -> Path:
    return fixture_root() / provider / f"{key.split(':', 1)[1]}.json.gz"


def load(provider: str, key: str) -> RawResponse:
    path = _path(provider, key)
    if not path.exists():
        raise FixtureMissing(
            f"No fixture for {provider} request {key}.\n"
            f"Expected at {path}.\n"
            f"Capture it with: python scripts/capture_fixtures.py --live"
        )
    payload = json.loads(gzip.decompress(path.read_bytes()))
    return RawResponse(
        provider=payload["provider"],
        endpoint=payload["endpoint"],
        params=payload["params"],
        status=payload["status"],
        body=json.dumps(payload["body"]).encode(),
        retrieved_at=datetime.fromisoformat(payload["captured_at"]),
        is_fixture=True,
    )


def save(key: str, response: RawResponse) -> Path:
    path = _path(response.provider, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    body: Any = json.loads(response.body) if response.body else None
    document = json.dumps(
        {
            "provider": response.provider,
            "endpoint": response.endpoint,
            "params": response.params,
            "status": response.status,
            "captured_at": response.retrieved_at.astimezone(UTC).isoformat(),
            "body": body,
        },
        indent=2,
        sort_keys=True,
    )
    # mtime=0 so the same response captured twice produces the same bytes, and re-running
    # a capture does not show up as a diff in every fixture it touched.
    path.write_bytes(gzip.compress(document.encode(), mtime=0))
    return path


def exists(provider: str, key: str) -> bool:
    return _path(provider, key).exists()
