"""The golden case scenario, as provider-shaped fixtures on disk.

**Why fixtures rather than seeded database rows.** The point of a regression lock is to
exercise the path the product actually runs: TronGrid payload → parser → canonical
transfer → trace → attribution → risk → report. Writing `Transfer` rows straight into the
database would skip retrieval and normalization, and those are two of the places a number
can silently change.

**The addresses are synthetic, and deliberately so.** Every one is generated from a fixed
seed through the real base58check encoder, so they are well-formed and impossible to
mistake for a wallet anyone owns. A golden case built on real addresses would be a
regression lock whose expected values change when the chain does — the opposite of a lock.
This is the "synthetic data is for tests only, flagged and never in the demo" rule in
CLAUDE.md principle 11: the demo uses real captured chain data, this test does not.

The shape it encodes is the one the product exists for:

    VICTIM ─40,000 USDT─▶ SCAM ┬─70%─▶ MULE_A ──▶ DEPOSIT ──▶ HOT (confirmed exchange)
                               ├─25%─▶ MULE_B ──▶ HOT
                               └── 5% dust, below the taint threshold, pruned
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.chains.tron import adapter as tron

# Fixed instant, so every timestamp in the expected output is stable for ever.
BASE = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def address(seed: int) -> str:
    """A well-formed TRON address from a fixed seed."""
    return tron.from_hex("41" + f"{seed:040x}")


VICTIM = address(0x11111)
SCAM = address(0x22222)
MULE_A = address(0x33333)
MULE_B = address(0x44444)
DUST = address(0x55555)
DEPOSIT = address(0x66666)
HOT = address(0x77777)

# 40,000 USDT at six decimals. Integer-exact everywhere; no float touches this number.
VICTIM_AMOUNT_RAW = 40_000_000_000

EXCHANGE_NAME = "Golden Exchange"

# One more than the FAN_IN detector's minimum, so the golden case covers the pattern
# stage rather than locking an empty list.
OTHER_SENDERS = 9


def _hash(label: str, index: int) -> str:
    """Deterministic, and obviously not a real transaction hash on inspection."""
    return f"{label}{index:02d}".encode().hex().ljust(64, "0")


def _minutes(offset: int) -> int:
    return int(BASE.timestamp() * 1000) + offset * 60_000


def _transfer(label: str, index: int, sender: str, recipient: str, raw: int, minute: int) -> dict:
    return {
        "transaction_id": _hash(label, index),
        "block_timestamp": _minutes(minute),
        "block_number": 60_000_000 + minute,
        "from": sender,
        "to": recipient,
        "type": "Transfer",
        "value": str(raw),
        "token_info": {"address": USDT, "decimals": 6, "symbol": "USDT", "name": "Tether USD"},
    }


def flows() -> list[dict[str, Any]]:
    """Every transfer in the scenario, in one list."""
    rows = [_transfer("victim", 0, VICTIM, SCAM, VICTIM_AMOUNT_RAW, 0)]

    # The scam wallet splits: two followed branches and one dust branch that is pruned.
    rows.append(_transfer("split", 0, SCAM, MULE_A, 28_000_000_000, 30))
    rows.append(_transfer("split", 1, SCAM, MULE_B, 10_000_000_000, 32))
    rows.append(_transfer("split", 2, SCAM, DUST, 2_000_000_000, 34))

    # Mule A layers through a deposit address; mule B goes straight to the hot wallet.
    rows.append(_transfer("mulea", 0, MULE_A, DEPOSIT, 28_000_000_000, 60))
    rows.append(_transfer("muleb", 0, MULE_B, HOT, 10_000_000_000, 65))

    # The deposit address sweeps onward, which is what makes it look like one.
    rows.append(_transfer("sweep", 0, DEPOSIT, HOT, 28_000_000_000, 75))

    # Unrelated senders into the deposit address: the many-in shape the funnel heuristic
    # keys on, and enough of them to trip the FAN_IN detector so the golden case locks the
    # pattern stage too. Small amounts, so the traced value is barely diluted — but it *is*
    # diluted, and that dilution is one of the numbers this case exists to lock.
    for i in range(OTHER_SENDERS):
        rows.append(_transfer("other", i, address(0x90000 + i), DEPOSIT, 1_000_000, 40 + i))
    return rows


def touching(rows: list[dict[str, Any]], subject: str) -> list[dict[str, Any]]:
    return [row for row in rows if subject in (row["from"], row["to"])]


ADDRESSES = [VICTIM, SCAM, MULE_A, MULE_B, DUST, DEPOSIT, HOT] + [
    address(0x90000 + i) for i in range(OTHER_SENDERS)
]


def write_fixtures(root: Path) -> None:
    """Write TronGrid-shaped fixtures for every address the trace can reach.

    Both endpoints are written for each address: the trace fetches native and TRC-20
    together, and a missing fixture fails the run loudly rather than looking like an
    address with no activity — which is the behaviour we want everywhere except here.
    """
    from app.ingestion.fixtures import fixture_key

    rows = flows()
    for subject in ADDRESSES:
        mine = touching(rows, subject)
        for endpoint, body in (
            (f"https://api.trongrid.io/v1/accounts/{subject}/transactions", {"data": []}),
            (
                f"https://api.trongrid.io/v1/accounts/{subject}/transactions/trc20",
                {"data": mine},
            ),
        ):
            params = {"limit": 200, "order_by": "block_timestamp,desc"}
            key = fixture_key("trongrid", endpoint, params)
            path = root / "trongrid" / f"{key.split(':', 1)[1]}.json.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            # Fixtures are stored gzipped; see app/ingestion/fixtures.py.
            path.write_bytes(
                gzip.compress(
                    json.dumps(
                        {
                            "provider": "trongrid",
                            "endpoint": endpoint,
                            "params": params,
                            "status": 200,
                            "captured_at": BASE.isoformat(),
                            "body": body,
                        },
                        indent=2,
                        sort_keys=True,
                    ).encode()
                )
            )
