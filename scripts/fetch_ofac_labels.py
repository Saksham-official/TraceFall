#!/usr/bin/env python
"""Regenerate data/labels/ofac_sanctioned.json from the published OFAC address lists.

The committed dataset is what the system ingests; this script exists so that dataset is
reproducible rather than hand-typed, and so its date can be refreshed. Run it whenever
the sanctions list should be brought current:

    python scripts/fetch_ofac_labels.py

Source: 0xB10C/ofac-sanctioned-digital-currency-addresses (MIT), which extracts the
digital-currency addresses from OFAC's SDN list nightly. The underlying SDN list is a US
Government publication. Licence assessment: docs/research/OQ-08-tron-label-coverage.md
section 3.

Every address is validated before it is written — a leading public label source was
measured at a 6% invalid-address rate, so an unvalidated ingest path is not acceptable
here (OQ-08).
"""

import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.chains import registry  # noqa: E402
from app.chains.base import InvalidAddressError  # noqa: E402
from app.db.models.enums import ChainCode  # noqa: E402

REPO = "https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses"
RAW = "https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/lists"

# TRX and ETH cover the two chains we support; the USDT list is included because OFAC
# designates some addresses only under the token they were used with, and those are the
# same TRON and Ethereum addresses we care about. The chain is decided by validating the
# address, never by which file it came from.
ASSET_LISTS = ("TRX", "ETH", "USDT")

OUTPUT = ROOT / "data" / "labels" / "ofac_sanctioned.json"

# The SDN designation names the sanctioned party, but the per-asset lists carry addresses
# only. Attributing an address to "a party on the SDN list" is exactly what this dataset
# supports, and no more.
# ponytail: parse SDN_ADVANCED.XML if per-party names are wanted; that is a ~50 MB
# download and a schema walk, for a nicer label on an already-correct finding.
ENTITY_NAME = "OFAC SDN designated party"


def fetch(asset: str) -> list[str]:
    url = f"{RAW}/sanctioned_addresses_{asset}.json"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        addresses: list[str] = json.load(response)
    print(f"  {asset}: {len(addresses)} addresses")
    return addresses


def main() -> int:
    seen: dict[tuple[ChainCode, str], str] = {}
    rejected: list[tuple[str, str]] = []
    skipped_chains = 0

    for asset in ASSET_LISTS:
        for address in fetch(asset):
            try:
                validated = registry.validate(address)
            except InvalidAddressError as exc:
                # Addresses for chains we do not support are the expected case in the
                # USDT list; a malformed TRON or Ethereum address is a real finding.
                if registry.detect_chain(address) is None:
                    skipped_chains += 1
                else:
                    rejected.append((address, str(exc)))
                continue
            seen[(validated.chain, validated.canonical)] = validated.display

    labels = [
        {
            "chain": str(chain),
            "address": canonical,
            "display": display,
            "entity": ENTITY_NAME,
            "entity_type": "SANCTIONED",
            "label_text": "OFAC SDN sanctioned address",
            "label_type": "SANCTIONED",
        }
        for (chain, canonical), display in sorted(
            seen.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
        )
    ]

    dataset = {
        "source": {
            "name": "OFAC SDN digital currency addresses",
            "url": REPO,
            "licence": (
                "Extractor MIT (0xB10C). Underlying SDN list is a US Government "
                "publication, free to reproduce."
            ),
            "reliability": "HIGH",
            "dataset_date": datetime.now(UTC).date().isoformat(),
            "description": (
                "Digital-currency addresses designated by the US Office of Foreign Asset "
                "Control, extracted nightly from the SDN list. Sanctions designations "
                "only — this dataset names no exchanges."
            ),
        },
        "labels": labels,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2) + "\n")

    by_chain: dict[str, int] = {}
    for label in labels:
        by_chain[str(label["chain"])] = by_chain.get(str(label["chain"]), 0) + 1
    print(f"\nwrote {len(labels)} labels to {OUTPUT.relative_to(ROOT)}: {by_chain}")
    print(f"skipped {skipped_chains} addresses on unsupported chains")
    if rejected:
        print(f"\nREJECTED {len(rejected)} malformed TRON/Ethereum addresses:")
        for address, reason in rejected:
            print(f"  {address}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
