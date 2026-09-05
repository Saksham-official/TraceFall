#!/usr/bin/env python
"""Turn addresses an exchange publishes about itself into a committed label dataset.

    python scripts/curate_exchange_labels.py \
        --entity "CoinDCX" \
        --source-url "https://coindcx.com/proof-of-reserves" \
        --addresses TAbc... TDef...

Provenance is the exchange's own disclosure — first-party, which is the strongest there
is and needs no judgement about anyone else's compilation (see ADR-018, closed unadopted).
**Only paste addresses an exchange publishes about itself.** An address copied from a
third-party explorer or dataset does not belong here; the provenance recorded would be a
lie, and a wrong `CONFIRMED` sends a freeze request to the wrong institution.

Three things happen to every address before it is written, and each can reject it:

1. **base58check validation.** The best available public TRON label source was measured at
   a 6% invalid-address rate (OQ-08 §4). An address that fails is dropped and reported.
2. **Behavioural observation via TronGrid**, which we hold under assessed terms. This is
   what makes the label ours rather than a copy of someone's claim.
3. **Role assigned from that behaviour, never from the source.** Hot, collection and cold
   wallets behave differently, and the deposit-address inference sweeps *to* hot and
   collection wallets. The best public source demonstrably labels cold wallets as hot, and
   a cold wallet in that position produces a confident wrong answer.

Nothing is written until you have seen the table. Add `--write` when it looks right.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.chains import registry  # noqa: E402
from app.chains.base import InvalidAddressError  # noqa: E402
from app.db.models.enums import ChainCode  # noqa: E402

TRONGRID = "https://api.trongrid.io/v1/accounts/{address}"
OUTPUT_DIR = ROOT / "data" / "labels"

# TronGrid without a key sustains about 3 requests per second and suspends a caller that
# exceeds it (DATA_SOURCES.md §1, measured). Curating twenty addresses is not worth being
# throttled for, so calls are spaced and a 429 is retried rather than recorded as
# "unverified" — an address wrongly marked unverified is one a human then has to check by
# hand for no reason.
REQUEST_SPACING_SECONDS = 1.5
RETRY_BACKOFF_SECONDS = 12.0
MAX_ATTEMPTS = 4

# A hot wallet moves constantly in both directions; a collection wallet is overwhelmingly
# inbound; a cold wallet holds a great deal and moves rarely. These are the shapes measured
# on real exchange wallets in OQ-08 §4(a), not invented thresholds.
COLD_MIN_BALANCE_TRX = 100_000_000
BUSY_MIN_TRANSACTIONS = 10_000


@dataclass
class Observed:
    address: str
    reachable: bool
    balance_trx: float = 0.0
    transactions: int = 0
    note: str = ""

    @property
    def role(self) -> str:
        if not self.reachable:
            return "UNVERIFIED"
        if self.balance_trx >= COLD_MIN_BALANCE_TRX and self.transactions < BUSY_MIN_TRANSACTIONS:
            return "cold"
        if self.transactions >= BUSY_MIN_TRANSACTIONS:
            return "hot"
        return "collection"


def observe(address: str, timeout: float = 20.0) -> Observed:
    """Ask TronGrid what this address actually does, respecting its rate limit."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        seen = _observe_once(address, timeout)
        if seen.reachable or "429" not in seen.note:
            return seen
        if attempt < MAX_ATTEMPTS:
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  rate limited on {address}; waiting {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    return seen


def _observe_once(address: str, timeout: float) -> Observed:
    url = TRONGRID.format(address=address)
    # The URL is built from a constant and a base58check-validated address, so the scheme
    # cannot be anything but https — but assert it rather than rely on that reasoning.
    assert url.startswith("https://api.trongrid.io/")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return Observed(address, reachable=False, note=f"TronGrid unreachable: {exc}")

    rows = payload.get("data") or []
    if not rows:
        return Observed(address, reachable=False, note="TronGrid returned no account record")

    account = rows[0]
    return Observed(
        address=address,
        reachable=True,
        balance_trx=account.get("balance", 0) / 1_000_000,
        # `latest_opration_time` and friends vary by account shape; transaction volume is
        # the field that is always present in one form or another.
        transactions=int(account.get("free_net_usage", 0) or 0)
        + len(account.get("trc20", []) or []),
        note="observed",
    )


def curate(entity: str, source_url: str, addresses: list[str]) -> tuple[list[dict], list[str]]:
    labels: list[dict] = []
    rejected: list[str] = []

    for raw in addresses:
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            validated = registry.validate(candidate, ChainCode.TRON)
        except InvalidAddressError as exc:
            rejected.append(f"{candidate}: {exc}")
            continue

        seen = observe(validated.canonical)
        time.sleep(REQUEST_SPACING_SECONDS)
        labels.append(
            {
                "chain": str(ChainCode.TRON),
                "address": validated.canonical,
                "display": validated.display,
                "entity": entity,
                "entity_type": "EXCHANGE",
                "label_text": f"{entity} {seen.role} wallet",
                "label_type": "EXCHANGE",
                "_observed": {
                    "role": seen.role,
                    "balance_trx": round(seen.balance_trx, 2),
                    "reachable": seen.reachable,
                    "note": seen.note,
                },
            }
        )
    return labels, rejected


def dataset(entity: str, source_url: str, labels: list[dict]) -> dict:
    return {
        "source": {
            "name": f"{entity} published wallet disclosure",
            "url": source_url,
            "licence": (
                "First-party publication by the exchange. Addresses published by their own "
                "operator about their own wallets; no third-party compilation is involved."
            ),
            "reliability": "HIGH",
            "dataset_date": datetime.now(UTC).date().isoformat(),
            "description": (
                f"Wallet addresses {entity} publishes about itself, transcribed from the "
                f"disclosure at {source_url}, each validated with base58check and its role "
                f"assigned from behaviour observed directly on TronGrid."
            ),
        },
        # `_observed` is stripped: it is why we believe the role, not part of the label.
        "labels": [{k: v for k, v in label.items() if not k.startswith("_")} for label in labels],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity", required=True, help='e.g. "CoinDCX"')
    parser.add_argument("--source-url", required=True, help="the exchange's own disclosure page")
    parser.add_argument("--addresses", nargs="+", required=True)
    parser.add_argument("--write", action="store_true", help="write the dataset file")
    args = parser.parse_args()

    labels, rejected = curate(args.entity, args.source_url, args.addresses)

    print(f"\n{args.entity} — {args.source_url}\n")
    print(f"{'address':<36} {'role':<12} {'balance TRX':>14}  note")
    for label in labels:
        seen = label["_observed"]
        print(
            f"{label['address']:<36} {seen['role']:<12} {seen['balance_trx']:>14,.2f}  "
            f"{seen['note']}"
        )
    if rejected:
        print(f"\nREJECTED {len(rejected)}:")
        for line in rejected:
            print(f"  {line}")

    unverified = [x for x in labels if x["_observed"]["role"] == "UNVERIFIED"]
    if unverified:
        print(
            f"\n{len(unverified)} address(es) could not be observed. Their role is a guess, "
            f"so they are written as UNVERIFIED — review before trusting them."
        )

    if not args.write:
        print("\nNothing written. Re-run with --write when the table looks right.")
        return 0

    slug = "".join(c.lower() if c.isalnum() else "_" for c in args.entity).strip("_")
    path = OUTPUT_DIR / f"exchange_{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset(args.entity, args.source_url, labels), indent=2) + "\n")
    print(f"\nwrote {len(labels)} labels to {path.relative_to(ROOT)}")
    print("Load them with: docker compose exec api python -m app.cli load-labels")
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
