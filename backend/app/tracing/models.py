"""Trace value objects.

Taint is carried as `Fraction`, not float or Decimal, because the accounting invariant
(every unit of the victim's value is attributed, pruned or retained — never created) has
to hold *exactly*. Rounding to integers happens once, at the output boundary.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction

from app.chains.base import TimeWindow
from app.db.models.enums import TerminationReason, TraceDirection
from app.normalize.transfer import NormalizedTransfer

# The engine performs no I/O of its own: the orchestrator supplies these. That is what
# makes it fully testable offline, and what keeps network concerns out of the algorithm.
FetchTransfers = Callable[[str], Awaitable[list[NormalizedTransfer]]]
IsServiceBoundary = Callable[[str], Awaitable[bool]]


class PruneReason:
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    FANOUT_CAP = "FANOUT_CAP"
    DUST = "DUST"


@dataclass(frozen=True, slots=True)
class TraceParams:
    """Bounds that make the search terminate. See docs/WALLET_TRACING.md section 5.

    `asset_key` scopes the trace to a single asset, and is not optional in practice.
    Raw amounts are integers at each asset's own precision, so 40,000 USDT (6 decimals,
    4e10 raw) and 1 ETH (18 decimals, 1e18 raw) are not comparable numbers — pooling
    them into one taint ratio would produce a confident, meaningless answer. The victim
    sent one asset; we follow that asset.
    """

    asset_key: str | None = None
    max_depth: int = 3
    taint_threshold: Fraction = Fraction(1, 100)
    fanout_cap: int = 8
    edge_budget: int = 5_000
    address_budget: int = 60
    min_amount_raw: int = 0
    window: TimeWindow | None = None
    direction: TraceDirection = TraceDirection.FORWARD
    stop_at_services: bool = True


@dataclass
class TraceNode:
    address: str
    depth: int
    tainted_in: Fraction = Fraction(0)
    attributed_out: Fraction = Fraction(0)
    pruned_out: Fraction = Fraction(0)
    is_terminal: bool = False
    termination_reason: TerminationReason | None = None
    first_reached_at: datetime | None = None

    @property
    def retained(self) -> Fraction:
        """Value that stopped here: kept by the address, or lost to the haircut ratio."""
        return self.tainted_in - self.attributed_out - self.pruned_out

    @property
    def tainted_raw(self) -> int:
        return int(self.tainted_in)


@dataclass
class TraceEdge:
    from_address: str
    to_address: str
    asset_key: str
    asset_symbol: str | None
    asset_contract: str | None
    decimals: int | None
    total_amount_raw: int
    tainted_amount: Fraction
    transfer_count: int
    first_transfer_at: datetime
    last_transfer_at: datetime
    tx_hashes: list[str] = field(default_factory=list)

    @property
    def tainted_raw(self) -> int:
        return int(self.tainted_amount)


@dataclass
class PrunedBranch:
    """Nothing is silently dropped: an investigator must see what was not followed."""

    from_address: str
    to_address: str
    asset_key: str
    total_amount_raw: int
    tainted_amount: Fraction
    reason: str

    @property
    def tainted_raw(self) -> int:
        return int(self.tainted_amount)


@dataclass
class TracePath:
    addresses: list[str]
    attributed: Fraction
    terminal_reason: TerminationReason | None
    last_activity: datetime | None

    @property
    def hops(self) -> int:
        return len(self.addresses) - 1


@dataclass
class TraceResult:
    root: str
    original_amount: Fraction
    anchor_tx_hash: str | None
    params: TraceParams
    nodes: dict[str, TraceNode] = field(default_factory=dict)
    edges: list[TraceEdge] = field(default_factory=list)
    pruned: list[PrunedBranch] = field(default_factory=list)
    paths: list[TracePath] = field(default_factory=list)
    addresses_fetched: int = 0

    @property
    def terminals(self) -> list[TraceNode]:
        return [n for n in self.nodes.values() if n.is_terminal]

    @property
    def total_pruned(self) -> Fraction:
        return sum((p.tainted_amount for p in self.pruned), Fraction(0))

    @property
    def total_retained(self) -> Fraction:
        return sum((n.retained for n in self.nodes.values()), Fraction(0))

    @property
    def pruned_share(self) -> float:
        """Reported to the investigator: how much of the value was not followed."""
        if not self.original_amount:
            return 0.0
        return float(self.total_pruned / self.original_amount)
