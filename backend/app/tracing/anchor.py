"""Anchoring a trace to the victim's actual transaction.

The single highest-value input an investigator can give us. With the amount and time the
victim sent funds, we trace *that value*; without them we analyse everything the address
ever received, and the result is far noisier.

Tolerances are deliberately generous. Complainants misremember times, screenshots carry
local timezones, and fees change amounts — a tight window loses real matches. Where
several transfers fit, we return them all rather than guessing: silently anchoring to the
wrong transaction corrupts the entire trace while looking perfectly fine.

A token symbol is not an identity. Anyone can deploy a contract calling itself USDT, and
scam wallets are routinely dusted with lookalikes. Matching on symbol alone would let a
poisoned token capture the anchor, so an amount that matches across several contracts is
reported as ambiguous rather than resolved.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.normalize.transfer import NormalizedTransfer

TIME_TOLERANCE = timedelta(hours=24)
AMOUNT_TOLERANCE = Decimal("0.02")  # 2%


@dataclass(frozen=True)
class AnchorResult:
    transfer: NormalizedTransfer | None
    candidates: list[NormalizedTransfer]
    reason: str

    @property
    def anchored(self) -> bool:
        return self.transfer is not None


def _amount_matches(transfer: NormalizedTransfer, reported: Decimal) -> bool:
    actual = transfer.amount
    if actual is None or reported <= 0:
        return False
    return abs(actual - reported) / reported <= AMOUNT_TOLERANCE


def resolve(
    transfers: list[NormalizedTransfer],
    address: str,
    reported_amount: Decimal | None,
    reported_at: object | None,
    asset_symbol: str | None = None,
) -> AnchorResult:
    """Find the victim's inbound transfer among everything this address received."""
    if reported_amount is None:
        return AnchorResult(None, [], "NO_AMOUNT_REPORTED")

    inbound = [t for t in transfers if t.to_address == address and t.succeeded]
    if asset_symbol:
        inbound = [t for t in inbound if (t.asset_symbol or "").upper() == asset_symbol.upper()]

    candidates = [t for t in inbound if _amount_matches(t, reported_amount)]

    # Token symbols are not identities. Real captured data contains a "USDTT" token in the
    # same wallet as genuine USDT, and nothing stops a scam token from claiming the symbol
    # exactly. If the amount matches transfers of more than one contract, we must not pick
    # one — anchoring to a poisoned lookalike would trace the wrong asset entirely.
    contracts = {t.asset_contract for t in candidates}
    if len(contracts) > 1:
        return AnchorResult(None, candidates, "AMBIGUOUS_TOKEN_SYMBOL")

    if reported_at is not None:
        timed = [
            t
            for t in candidates
            if abs(t.block_time - reported_at) <= TIME_TOLERANCE  # type: ignore[operator]
        ]
        # Only narrow by time if it leaves something; a wrong timezone should not
        # discard an otherwise perfect amount match.
        if timed:
            candidates = timed

    if not candidates:
        return AnchorResult(None, [], "NO_MATCHING_TRANSFER")
    if len(candidates) == 1:
        return AnchorResult(candidates[0], candidates, "ANCHORED")
    return AnchorResult(None, candidates, "MULTIPLE_CANDIDATES")
