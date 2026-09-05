#!/usr/bin/env python
"""Measure the deposit-address heuristic against published ground truth.

    python scripts/measure_attribution_precision.py --positives 60 --negatives 40

**The gate this answers:** FR-71 and TESTING_STRATEGY.md §14 require precision ≥ 0.95 on
`PROBABLE` at the 0.7 confidence threshold. Until now that could not be measured, because
no labelled set existed. It does now: Binance publishes its own Ethereum deposit
addresses, so a positive is an address the operator *says* is a deposit address.

**Ground truth, and its limits.**

- **Positives** — addresses Binance publishes as deposit addresses in its proof-of-reserves
  disclosure. As good a label as exists.
- **Negatives** — Binance's own hot and cold wallets from the same disclosure. These are
  *hard* negatives on purpose: they are the addresses a deposit address sweeps *to*, they
  are exchange-operated, and they see enormous volume. If the heuristic cannot tell a
  deposit address from the wallet it feeds, it is not usable. Easy negatives (a random
  personal wallet) would flatter the number and teach us nothing.

**What this cannot tell us.** The look-alikes that actually cost precision in the field —
payment processors, custodial services, OTC desks — are absent from this set, and
LIMITATIONS.md §7 already says they are scarce in any dataset we can assemble. A high
number here is evidence the heuristic separates deposit addresses from exchange wallets.
It is not evidence it separates them from a payment processor, and this script must not be
cited as if it were.

Ethereum, not TRON, because Binance's disclosure contains 2.3 million Ethereum deposit
addresses and **no TRON ones at all** — checked, not assumed.
"""

import argparse
import asyncio
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.attribution.decision import DEPOSIT_THRESHOLD, funnel_score  # noqa: E402
from app.db.models.enums import ChainCode, TransferStatus  # noqa: E402
from app.intel.features import extract  # noqa: E402
from app.normalize.transfer import NormalizedTransfer  # noqa: E402

BLOCKSCOUT = "https://eth.blockscout.com/api"
# The same identifier the application sends. Blockscout's CDN returns 403 to the default
# `Python-urllib` agent, which looks exactly like an outage if you do not check the body.
USER_AGENT = "TraceFall/0.1 (blockchain investigation research)"
# Measured at no throttling up to 11.8 req/s (OQ-01); this stays well under that.
SPACING_SECONDS = 0.25
PAGE_SIZE = 200


@dataclass
class Outcome:
    address: str
    truth: str
    transfers: int
    score: float
    predicted_deposit: bool
    reason: str = ""


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        tp = sum(1 for o in self.outcomes if o.truth == "deposit" and o.predicted_deposit)
        fp = sum(1 for o in self.outcomes if o.truth != "deposit" and o.predicted_deposit)
        fn = sum(1 for o in self.outcomes if o.truth == "deposit" and not o.predicted_deposit)
        tn = sum(1 for o in self.outcomes if o.truth != "deposit" and not o.predicted_deposit)
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}

    def precision(self) -> float | None:
        c = self.counts()
        predicted = c["tp"] + c["fp"]
        return None if predicted == 0 else c["tp"] / predicted

    def recall(self) -> float | None:
        c = self.counts()
        actual = c["tp"] + c["fn"]
        return None if actual == 0 else c["tp"] / actual


def fetch(address: str) -> list[dict[str, Any]] | None:
    """One page of ERC-20 transfers. None means the request failed."""
    query = urllib.parse.urlencode(
        {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": 1,
            "offset": PAGE_SIZE,
            "sort": "asc",
        }
    )
    url = f"{BLOCKSCOUT}?{query}"
    assert url.startswith("https://eth.blockscout.com/")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    result = payload.get("result")
    return result if isinstance(result, list) else []


def to_transfers(address: str, rows: list[dict[str, Any]]) -> list[NormalizedTransfer]:
    """Blockscout rows to the canonical value object the feature extractor consumes."""
    transfers = []
    for index, row in enumerate(rows):
        try:
            transfers.append(
                NormalizedTransfer(
                    chain=ChainCode.ETHEREUM,
                    tx_hash=str(row["hash"]),
                    transfer_index=index,
                    block_number=int(row.get("blockNumber", 0)),
                    block_time=datetime.fromtimestamp(int(row["timeStamp"]), tz=UTC),
                    from_address=str(row["from"]).lower(),
                    to_address=str(row["to"]).lower(),
                    amount_raw=int(row["value"]),
                    status=TransferStatus.SUCCESS,
                    asset_symbol=row.get("tokenSymbol") or None,
                    asset_contract=str(row.get("contractAddress", "")).lower() or None,
                    decimals=int(row["tokenDecimal"]) if row.get("tokenDecimal") else None,
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return transfers


def assess(address: str, truth: str) -> Outcome:
    rows = fetch(address)
    time.sleep(SPACING_SECONDS)
    if rows is None:
        return Outcome(address, truth, 0, 0.0, False, "provider request failed")
    if not rows:
        return Outcome(address, truth, 0, 0.0, False, "no transfers returned")

    transfers = to_transfers(address.lower(), rows)
    features = extract(address.lower(), transfers)
    if not features.has_sufficient_activity:
        return Outcome(
            address, truth, len(transfers), 0.0, False,
            f"insufficient activity ({features.tx_count_in} in, {features.tx_count_out} out)",
        )
    score, _ = funnel_score(features)
    value = float(score)
    return Outcome(address, truth, len(transfers), value, value >= float(DEPOSIT_THRESHOLD))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positives", type=int, default=60)
    parser.add_argument("--negatives", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260905, help="fixed, so this is repeatable")
    parser.add_argument("--positives-file", default="/tmp/eth_deposits.txt")
    parser.add_argument("--negatives-file", default="/tmp/eth_hotcold.txt")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    positives = Path(args.positives_file).read_text().split()
    negatives = Path(args.negatives_file).read_text().split()
    sample = [(a, "deposit") for a in rng.sample(positives, min(args.positives, len(positives)))]
    sample += [(a, "exchange") for a in rng.sample(negatives, min(args.negatives, len(negatives)))]
    rng.shuffle(sample)

    report = Report()
    for index, (address, truth) in enumerate(sample, start=1):
        outcome = assess(address, truth)
        report.outcomes.append(outcome)
        print(
            f"  [{index:>3}/{len(sample)}] {address} truth={truth:<9} "
            f"score={outcome.score:.2f} predicted={'deposit' if outcome.predicted_deposit else '-':<8}"
            f" {outcome.reason}",
            flush=True,
        )

    counts = report.counts()
    precision = report.precision()
    recall = report.recall()
    print("\n" + "=" * 72)
    print(f"threshold: {float(DEPOSIT_THRESHOLD):.2f}   sample: {len(sample)}   seed: {args.seed}")
    print(f"true positives  {counts['tp']:>4}   false positives {counts['fp']:>4}")
    print(f"false negatives {counts['fn']:>4}   true negatives  {counts['tn']:>4}")
    print(f"\nprecision: {'n/a' if precision is None else f'{precision:.3f}'}   (gate: >= 0.95)")
    print(f"recall:    {'n/a' if recall is None else f'{recall:.3f}'}")
    unscored = [o for o in report.outcomes if o.reason]
    print(f"\nnot scored: {len(unscored)} — {'; '.join(sorted({o.reason for o in unscored}))}")
    print(
        "\nNegatives here are Binance's own hot and cold wallets. Payment processors and\n"
        "custodial services — the look-alikes that actually cost precision — are not in\n"
        "this set. See LIMITATIONS.md section 7."
    )

    if precision is None:
        return 2
    return 0 if precision >= 0.95 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
