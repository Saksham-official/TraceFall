#!/usr/bin/env python
"""Capture real provider responses as committed fixtures.

Fixtures are real chain data, frozen — not mock data. They give a demo that runs with no
network and tests that are deterministic over real-world messiness (ADR-009).

    LIVE_MODE=true python scripts/capture_fixtures.py --chain TRON --address TXn8...

Run from the backend directory, or with backend on PYTHONPATH.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

# Capture only makes sense against the network.
os.environ["LIVE_MODE"] = "true"

from app.chains.base import TimeWindow  # noqa: E402
from app.db.models.enums import ChainCode  # noqa: E402
from app.ingestion import fixtures, service  # noqa: E402
from app.ingestion.http import close_http_client  # noqa: E402


async def capture(chain: ChainCode, address: str, days: int) -> int:
    window = TimeWindow.last_days(days)
    data = await service.retrieve_address(chain, address, window)
    written = 0
    for response in data.responses:
        key = fixtures.fixture_key(response.provider, response.endpoint, response.params)
        path = fixtures.save(key, response)
        written += 1
        print(f"  {path.name}  ({len(response.body)} bytes)  {response.provider}")
    print(
        f"{chain} {address}: {data.record_count} records, "
        f"{written} responses, complete={data.complete}"
    )
    if data.degradations:
        print(f"  degraded: {data.degradations}")
    return written


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain", choices=[c.value for c in ChainCode], required=True)
    parser.add_argument("--address", required=True, action="append", dest="addresses")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    total = 0
    for address in args.addresses:
        total += await capture(ChainCode(args.chain), address, args.days)
    await close_http_client()
    print(f"\ncaptured {total} fixture responses into {fixtures.fixture_root()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
