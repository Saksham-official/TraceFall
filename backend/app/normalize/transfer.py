"""The canonical value object: one transfer, chain-agnostic.

**This is the interface between normalization (Phase 4) and everything downstream.**
The normalizer produces these; the tracing, graph, pattern and risk engines consume them
and never see a provider payload or a chain-specific field.

Amounts are exact integers at raw chain precision. There is no float anywhere in this
path — a float would silently corrupt a large token amount, and these numbers end up in
a police report.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.db.models.enums import ChainCode, TransferStatus


@dataclass(frozen=True, slots=True)
class NormalizedTransfer:
    """One value movement between two addresses.

    A single transaction moving ETH and emitting three token events produces four of
    these, sharing `tx_hash` and distinguished by `transfer_index`. That uniformity is
    what lets the tracing engine treat every chain identically.
    """

    chain: ChainCode
    tx_hash: str
    transfer_index: int
    block_number: int
    # Always timezone-aware UTC.
    block_time: datetime
    # Canonical form: TRON base58 as-is, Ethereum lowercase hex.
    from_address: str
    to_address: str
    # Exact, at raw chain precision. Never a float.
    amount_raw: int
    status: TransferStatus
    # None for a token the system has not identified yet. Never guessed.
    asset_symbol: str | None = None
    # None for native currency (TRX, ETH).
    asset_contract: str | None = None
    # None when unknown; display must then be suppressed rather than wrong.
    decimals: int | None = None
    fee_raw: int | None = None
    is_internal: bool = False

    @property
    def asset_key(self) -> str:
        """Identity used to group flows of the same asset."""
        return f"{self.chain}:{self.asset_contract or 'native'}"

    @property
    def amount(self) -> Decimal | None:
        """Human-readable amount, or None when decimals are unknown.

        Returning None is deliberate: showing a 6-decimal token as if it had 18 would
        understate the amount by a factor of a trillion.
        """
        if self.decimals is None:
            return None
        return Decimal(self.amount_raw) / (Decimal(10) ** self.decimals)

    @property
    def succeeded(self) -> bool:
        return self.status is TransferStatus.SUCCESS

    @property
    def identity(self) -> tuple[str, str, int]:
        """Idempotency key — re-ingesting the same chain data must be a no-op."""
        return (str(self.chain), self.tx_hash, self.transfer_index)
