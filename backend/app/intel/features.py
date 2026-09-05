"""Behavioural features for one address, computed from its transfers.

Pure computation: no network, no database. The signals are the ones named in
VASP_IDENTIFICATION.md section 4, and they exist to answer one question — does this
address behave like an exchange deposit address, which receives from many unrelated
senders and sweeps everything onward to one destination?

Two deliberate choices:

**Value-weighted signals are scoped to a single asset.** Raw amounts are integers at each
asset's own precision, so 40,000 USDT (6 decimals) and 1 ETH (18 decimals) are not
comparable numbers. Pooling them into one sweep ratio produces a confident, meaningless
answer — the same reasoning that scopes a trace to one asset.

**Ratios are `Fraction`, not float.** These feed a confidence that reaches a police
report, and the amounts they divide are exact integers.

Failed transfers stay in the database (they are evidence of an attempt) but are excluded
here, because a transfer that reverted moved no value and describes no behaviour.
"""

import statistics
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from app.normalize.transfer import NormalizedTransfer

# Section 7 step 3: below this there is not enough behaviour to classify, and the honest
# answer is UNATTRIBUTED with a reason — not a low score.
MIN_INBOUND_FOR_PROFILE = 3
MIN_OUTBOUND_FOR_PROFILE = 1


@dataclass(frozen=True, slots=True)
class AddressFeatures:
    """What the address does, stated as measurements rather than conclusions."""

    address: str
    # The asset the value-weighted signals were computed over.
    asset_key: str | None

    tx_count_in: int
    tx_count_out: int
    counterparty_diversity_in: int
    counterparty_diversity_out: int
    total_in_raw: int
    total_out_raw: int
    distinct_assets: int

    # None where the address gives no basis to compute it. None is not zero: "we could
    # not measure this" and "we measured it as nothing" lead to different findings.
    sweep_consistency: Fraction | None
    sweep_ratio: Fraction | None
    balance_retention: Fraction | None
    median_dwell_seconds: int | None
    # The single destination taking the largest share of outbound value — the address the
    # chained inference in VASP_IDENTIFICATION.md section 4 asks about next.
    dominant_out_destination: str | None
    initiates_transfers: bool
    # Not computable from transfers alone; it needs contract knowledge we do not hold at
    # this stage. Carried as None so it is reported as not evaluated, never as zero.
    contract_interaction_rate: Fraction | None = None

    @property
    def has_sufficient_activity(self) -> bool:
        return (
            self.tx_count_in >= MIN_INBOUND_FOR_PROFILE
            and self.tx_count_out >= MIN_OUTBOUND_FOR_PROFILE
        )

    @property
    def is_high_volume_bidirectional(self) -> bool:
        """The section 7 step 5 shape: a busy hub moving value both ways."""
        return (
            self.tx_count_in >= 1_000
            and self.tx_count_out >= 1_000
            and self.counterparty_diversity_in >= 100
            and self.counterparty_diversity_out >= 100
        )

    def as_dict(self) -> dict[str, object]:
        """JSONB-safe form for `address_profiles.features`."""
        return {
            "asset_key": self.asset_key,
            "tx_count_in": self.tx_count_in,
            "tx_count_out": self.tx_count_out,
            "counterparty_diversity_in": self.counterparty_diversity_in,
            "counterparty_diversity_out": self.counterparty_diversity_out,
            "total_in_raw": str(self.total_in_raw),
            "total_out_raw": str(self.total_out_raw),
            "distinct_assets": self.distinct_assets,
            "sweep_consistency": _as_float(self.sweep_consistency),
            "sweep_ratio": _as_float(self.sweep_ratio),
            "balance_retention": _as_float(self.balance_retention),
            "median_dwell_seconds": self.median_dwell_seconds,
            "dominant_out_destination": self.dominant_out_destination,
            "initiates_transfers": self.initiates_transfers,
            "contract_interaction_rate": _as_float(self.contract_interaction_rate),
        }


def _as_float(value: Fraction | None) -> float | None:
    """Only for display and storage of a ratio — never on the amount path."""
    return None if value is None else float(value)


def extract(
    address: str, transfers: list[NormalizedTransfer], asset_key: str | None = None
) -> AddressFeatures:
    """Compute the section 4 signals for `address`.

    `asset_key` scopes the value-weighted signals. When omitted, the address's most
    active asset is used, which is the right default for an address that only ever
    handles one token — the deposit-address case.
    """
    moved = [t for t in transfers if t.succeeded]
    if asset_key is None:
        asset_key = _dominant_asset(moved, address)

    scoped = [t for t in moved if t.asset_key == asset_key] if asset_key else []
    inbound = sorted(
        (t for t in scoped if t.to_address == address), key=lambda t: (t.block_time, t.tx_hash)
    )
    outbound = sorted(
        (t for t in scoped if t.from_address == address), key=lambda t: (t.block_time, t.tx_hash)
    )

    total_in = sum(t.amount_raw for t in inbound)
    total_out = sum(t.amount_raw for t in outbound)

    return AddressFeatures(
        address=address,
        asset_key=asset_key,
        tx_count_in=len(inbound),
        tx_count_out=len(outbound),
        counterparty_diversity_in=len({t.from_address for t in inbound}),
        counterparty_diversity_out=len({t.to_address for t in outbound}),
        total_in_raw=total_in,
        total_out_raw=total_out,
        distinct_assets=len({t.asset_key for t in moved}),
        sweep_consistency=_sweep_consistency(outbound, total_out),
        sweep_ratio=_sweep_ratio(inbound, outbound),
        balance_retention=_balance_retention(total_in, total_out),
        median_dwell_seconds=_median_dwell(inbound, outbound),
        dominant_out_destination=_dominant_destination(outbound),
        initiates_transfers=bool(outbound)
        and (not inbound or outbound[0].block_time < inbound[0].block_time),
    )


def _dominant_asset(transfers: list[NormalizedTransfer], address: str) -> str | None:
    touching = [t for t in transfers if address in (t.from_address, t.to_address)]
    if not touching:
        return None
    # Ties broken by asset key so the result is deterministic across runs.
    counts = Counter(t.asset_key for t in touching)
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _by_destination(outbound: list[NormalizedTransfer]) -> Counter[str]:
    totals: Counter[str] = Counter()
    for transfer in outbound:
        totals[transfer.to_address] += transfer.amount_raw
    return totals


def _sweep_consistency(outbound: list[NormalizedTransfer], total_out: int) -> Fraction | None:
    """Share of outbound value going to the single largest destination."""
    if not outbound or total_out == 0:
        return None
    return Fraction(max(_by_destination(outbound).values()), total_out)


def _dominant_destination(outbound: list[NormalizedTransfer]) -> str | None:
    if not outbound:
        return None
    totals = _by_destination(outbound)
    return min(totals.items(), key=lambda item: (-item[1], item[0]))[0]


def _sweep_ratio(
    inbound: list[NormalizedTransfer], outbound: list[NormalizedTransfer]
) -> Fraction | None:
    """Median share of the balance that each outbound transfer moved.

    A deposit address forwards essentially everything it holds, so this sits near 1.
    The balance is replayed from the transfers we hold, which is a lower bound when
    retrieval was partial — that direction is safe: it understates the ratio rather than
    inventing a sweep.
    """
    events = [(t.block_time, t.tx_hash, t.amount_raw) for t in inbound]
    events += [(t.block_time, t.tx_hash, -t.amount_raw) for t in outbound]
    events.sort(key=lambda e: (e[0], e[1]))

    balance = 0
    ratios: list[Fraction] = []
    for _, _, delta in events:
        if delta < 0:
            available = balance
            if available > 0:
                ratios.append(min(Fraction(-delta, available), Fraction(1)))
        balance += delta
    return statistics.median(ratios) if ratios else None


def _balance_retention(total_in: int, total_out: int) -> Fraction | None:
    """Share of received value still held. A deposit address keeps almost none."""
    if total_in == 0:
        return None
    return max(Fraction(total_in - total_out, total_in), Fraction(0))


def _median_dwell(
    inbound: list[NormalizedTransfer], outbound: list[NormalizedTransfer]
) -> int | None:
    """Median seconds from a receipt to the next outbound transfer."""
    gaps = []
    for transfer in outbound:
        preceding = [t for t in inbound if t.block_time <= transfer.block_time]
        if preceding:
            gaps.append(int((transfer.block_time - preceding[-1].block_time).total_seconds()))
    return int(statistics.median(gaps)) if gaps else None
