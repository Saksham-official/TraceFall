#!/usr/bin/env python
"""Capture — and then verify — the fixtures the demo traces need.

    python scripts/demo_fixtures.py --check       # offline: is anything missing?
    python scripts/demo_fixtures.py               # live: capture what is

`capture_fixtures.py` captures one address. A trace does not stop at one address: it
follows the money, and every address it reaches is another provider request. In fixture
mode a hop with no committed fixture ends that branch as `DATA_UNAVAILABLE` (ADR-019) —
honest, but a demo that shows honest gaps where it meant to show a fund flow is a demo
that undersells the product.

So this **runs the real tracer**. `tracing.engine.trace` is pure and takes a fetch
callback, so the same engine the pipeline runs walks the same addresses here, with the
same taint threshold, the same fan-out cap and the same budgets. Capture fetches through
that callback and commits what comes back; the check reads fixtures through it and reports
every `DATA_UNAVAILABLE`. Nothing is captured that the trace would not ask for, and
nothing the trace asks for is missed.

Two deliberate differences from the pipeline, both of which make this a superset:

- **No service-boundary check**, because that needs the database. The trace therefore
  continues past an address the pipeline would stop at, so the fixture set covers more
  than the demo will read.
- **No anchor.** A demo case with a reported amount traces a smaller slice than the whole
  inbound total this walks.

One difference cuts the other way and the check cannot close it. The pipeline reads each
address's transfers back from the database, so it sees transfers that arrived in *another*
address's response — which matters exactly where a busy address was truncated at the
10,000-transfer retrieval cap, and its counterparty's response carries an edge its own does
not. This script only ever sees one address's own responses, so the pipeline can reach a
hop the check did not. **Run each demo case once after checking**, and capture anything its
graph reports under `unavailable_addresses`:

    python scripts/demo_fixtures.py --address <the one it named> --depth 0

**`--check` is the pre-flight gate** ([DEPLOYMENT.md §5](../docs/DEPLOYMENT.md)). It runs
with `LIVE_MODE=false`, makes no network call, writes nothing, and exits non-zero naming
every address the demo would hit a gap on.

The addresses live in `config/demo_addresses.yaml`, which is also what DEMO_SCRIPT.md
walks through — one list, so the rehearsal and the check cannot drift apart.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEMO_ADDRESSES = ROOT / "config" / "demo_addresses.yaml"

# Set before importing anything that reads settings: the mode decides whether this script
# touches the network at all.
_CHECK = "--check" in sys.argv
os.environ["LIVE_MODE"] = "false" if _CHECK else "true"

# `--check` is the pre-flight gate and runs on the presentation machine, where a clean
# shell has no SECRET_KEY. It signs nothing and serves no request, so a throwaway value
# beats greeting the operator with a pydantic traceback thirty seconds before the demo.
# Never defaulted in the app itself (principle 10) — only here, and only offline.
if _CHECK:
    os.environ.setdefault("SECRET_KEY", "check-only-" + "0" * 32)

import yaml  # noqa: E402

from app.chains.base import TimeWindow  # noqa: E402
from app.db.models.enums import ChainCode  # noqa: E402
from app.ingestion import fixtures, service  # noqa: E402
from app.ingestion.fixtures import FixtureMissing  # noqa: E402
from app.ingestion.http import close_http_client  # noqa: E402
from app.intel import features as intel_features  # noqa: E402
from app.normalize import parsers  # noqa: E402
from app.normalize.transfer import NormalizedTransfer  # noqa: E402
from app.tracing.engine import trace  # noqa: E402
from app.tracing.models import FetchTransfers, TraceParams, TransfersUnavailable  # noqa: E402


def known_labels() -> dict[str, str]:
    """Committed labels, so the walk can report when it reaches an identified service."""
    found: dict[str, str] = {}
    for path in sorted((ROOT / "data" / "labels").glob("*.json")):
        for label in json.loads(path.read_text())["labels"]:
            found[label["address"]] = f"{label['entity']} ({label['entity_type']})"
    return found


def demo_config() -> dict[str, object]:
    if not DEMO_ADDRESSES.exists():
        raise SystemExit(f"{DEMO_ADDRESSES} does not exist; name the addresses with --address")
    loaded: dict[str, object] = yaml.safe_load(DEMO_ADDRESSES.read_text())
    return loaded


async def load(
    chain: ChainCode, address: str, window: TimeWindow, save: bool
) -> list[NormalizedTransfer]:
    """One address's transfers, through the pipeline's own retrieval and parser."""
    data = await service.retrieve_address(chain, address, window)
    if save:
        for response in data.responses:
            key = fixtures.fixture_key(response.provider, response.endpoint, response.params)
            fixtures.save(key, response)
    return [t for t in parsers.parse(data) if t.succeeded]


def fetcher(
    chain: ChainCode, window: TimeWindow, save: bool, already: set[str]
) -> FetchTransfers:
    """The engine's fetch callback. Mirrors `worker._fetcher` without the database."""

    async def fetch(address: str) -> list[NormalizedTransfer]:
        if address in already:
            # The root was fetched to pick the asset; the engine asks for it again.
            return await load(chain, address, window, save=False)
        try:
            transfers = await load(chain, address, window, save)
        except FixtureMissing:
            # Exactly what the pipeline does: the branch ends as DATA_UNAVAILABLE rather
            # than as the much stronger claim that the funds stopped here.
            raise TransfersUnavailable(address, "no fixture is committed") from None
        print(f"    {address} transfers={len(transfers)}", flush=True)
        return transfers

    return fetch


async def walk(chain: ChainCode, root: str, days: int, depth: int, save: bool) -> dict[str, object]:
    window = TimeWindow.last_days(days)
    labels = known_labels()

    try:
        transfers = await load(chain, root, window, save)
    except FixtureMissing:
        print(f"    {root} NO FIXTURE (the root itself)", flush=True)
        return {"root": root, "addresses": 0, "missing": [root], "labelled": {}, "terminals": []}
    print(f"    {root} transfers={len(transfers)}", flush=True)

    # What the pipeline traces when the case carries no reported amount: everything the
    # root received in the asset it handles most, chosen by transfer count.
    asset_key = intel_features.dominant_asset(transfers, root)
    amount = sum(
        t.amount_raw for t in transfers if t.to_address == root and t.asset_key == asset_key
    )
    if asset_key is None or amount <= 0:
        return {
            "root": root,
            "addresses": 1,
            "missing": [],
            "labelled": {},
            "terminals": [],
            "note": "the root received nothing traceable in the window",
        }

    result = await trace(
        root,
        amount,
        fetcher(chain, window, save, {root}),
        TraceParams(asset_key=asset_key, max_depth=depth, window=window),
    )
    return {
        "root": root,
        "asset": asset_key,
        "addresses": len(result.nodes),
        "edges": len(result.edges),
        "missing": [u["address"] for u in result.unavailable],
        "labelled": {a: labels[a] for a in result.nodes if a in labels},
        "terminals": [
            f"{node.address} {node.termination_reason}"
            for node in result.nodes.values()
            if node.is_terminal
        ],
        "pruned_share": round(float(result.pruned_share), 4),
    }


async def main() -> int:
    config = demo_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify offline instead of capturing; non-zero exit if a fixture is missing",
    )
    parser.add_argument("--chain", choices=[c.value for c in ChainCode], default="TRON")
    parser.add_argument(
        "--address",
        action="append",
        dest="addresses",
        help="defaults to every address in config/demo_addresses.yaml",
    )
    # The demo's own settings, so the fixture and the analysis ask for the same slice.
    parser.add_argument("--days", type=int, default=int(config.get("window_days", 90)))  # type: ignore[arg-type]
    parser.add_argument("--depth", type=int, default=int(config.get("max_depth", 3)))  # type: ignore[arg-type]
    args = parser.parse_args()

    targets: list[dict[str, str]] = (
        [{"address": a, "chain": args.chain} for a in args.addresses]
        if args.addresses
        else list(config["addresses"])  # type: ignore[arg-type]
    )

    summaries = []
    for target in targets:
        print(f"\n{target['address']}  {target.get('role', '')}", flush=True)
        summary = await walk(
            ChainCode(target.get("chain", args.chain)),
            target["address"],
            args.days,
            args.depth,
            save=not args.check,
        )
        summary["expect"] = target.get("expect")
        summaries.append(summary)
    await close_http_client()

    print(f"\nfixtures in {fixtures.fixture_root()}")
    gaps: list[str] = []
    drifted: list[str] = []
    for summary in summaries:
        missing = summary["missing"]
        assert isinstance(missing, list)
        gaps.extend(missing)
        note = f"  — {summary['note']}" if summary.get("note") else ""
        print(
            f"  {summary['root']}: {summary['addresses']} addresses, "
            f"{summary.get('edges', 0)} edges, {len(missing)} missing{note}"
        )
        for address, label in summary["labelled"].items():  # type: ignore[union-attr]
            print(f"      {address}  {label}")
        for line in summary["terminals"]:  # type: ignore[union-attr]
            print(f"      ends: {line}")
        for address in missing:
            print(f"      MISSING {address}")
        expect = summary.get("expect")
        if isinstance(expect, dict):
            got = {"addresses": summary["addresses"], "edges": summary.get("edges", 0)}
            if any(got[k] != v for k, v in expect.items()):
                drifted.append(f"{summary['root']}: expected {expect}, got {got}")
                print(f"      DRIFTED from expected {expect}")

    if args.check and drifted:
        print(
            f"\n{len(drifted)} demo case(s) no longer trace what DEMO_SCRIPT.md describes:\n  "
            + "\n  ".join(drifted)
            + "\n\nA fixture is a frozen snapshot but the window slides, so a case can shrink "
            "with nothing failing.\nEither widen `window_days`, recapture the fixtures, or "
            "update `expect` in config/demo_addresses.yaml\nand say in the commit why the "
            "number moved."
        )
        return 1
    if args.check and gaps:
        print(
            f"\n{len(gaps)} address(es) have no committed fixture; the demo would show "
            f"DATA_UNAVAILABLE there.\nCapture them with:\n  python scripts/demo_fixtures.py "
            + " ".join(f"--address {a}" for a in dict.fromkeys(gaps))
        )
        return 1
    if args.check:
        print("\nEvery address the demo traces has a committed fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
