"""Fund flow tracing — the core of TraceFall.

Breadth-first, depth by depth, ordered by attributed value, with proportional (haircut)
attribution at every hop. See docs/WALLET_TRACING.md for the full design.

The engine performs no I/O: the caller supplies a transfer-fetching callback and a
service-boundary predicate. That keeps the algorithm pure, fully testable offline, and
free of any chain-specific knowledge.

Two properties are load-bearing:

* **It always terminates.** Five independent bounds — depth, fan-out cap, taint
  threshold, edge budget and address budget — mean worst-case exploration is a known
  constant rather than a function of chain size.
* **It never creates value.** Everything that is not followed is recorded as pruned, so
  the accounting invariant holds exactly and an investigator can see what the algorithm
  chose to ignore.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction

from app.db.models.enums import TerminationReason, TraceDirection
from app.normalize.transfer import NormalizedTransfer
from app.tracing import invariants, taint
from app.tracing.models import (
    FetchTransfers,
    IsServiceBoundary,
    PrunedBranch,
    PruneReason,
    TraceEdge,
    TraceNode,
    TraceParams,
    TracePath,
    TraceResult,
)

log = logging.getLogger(__name__)


@dataclass
class _Flow:
    """Outbound transfers to one counterparty, aggregated. Twenty transfers, one edge."""

    counterparty: str
    asset_key: str
    asset_symbol: str | None
    asset_contract: str | None
    decimals: int | None
    total_raw: int = 0
    count: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    tx_hashes: list[str] = field(default_factory=list)

    def add(self, transfer: NormalizedTransfer) -> None:
        self.total_raw += transfer.amount_raw
        self.count += 1
        if self.first_at is None or transfer.block_time < self.first_at:
            self.first_at = transfer.block_time
        if self.last_at is None or transfer.block_time > self.last_at:
            self.last_at = transfer.block_time
        if len(self.tx_hashes) < 50:  # enough to drill down; not the whole history
            self.tx_hashes.append(transfer.tx_hash)


def _source(transfer: NormalizedTransfer, direction: TraceDirection) -> str:
    return transfer.from_address if direction is TraceDirection.FORWARD else transfer.to_address


def _target(transfer: NormalizedTransfer, direction: TraceDirection) -> str:
    return transfer.to_address if direction is TraceDirection.FORWARD else transfer.from_address


def _eligible(transfers: list[NormalizedTransfer], params: TraceParams) -> list[NormalizedTransfer]:
    """Window, asset and success filtering, applied once."""
    out = []
    for t in transfers:
        if not t.succeeded:
            continue
        if params.asset_key is not None and t.asset_key != params.asset_key:
            continue
        if params.window is not None and not (
            params.window.start <= t.block_time <= params.window.end
        ):
            continue
        out.append(t)
    return out


async def trace(
    root: str,
    original_amount: int,
    fetch: FetchTransfers,
    params: TraceParams | None = None,
    is_service_boundary: IsServiceBoundary | None = None,
    anchor_tx_hash: str | None = None,
    anchor_time: datetime | None = None,
) -> TraceResult:
    params = params or TraceParams()
    result = TraceResult(
        root=root,
        original_amount=Fraction(original_amount),
        anchor_tx_hash=anchor_tx_hash,
        params=params,
    )
    root_node = TraceNode(
        address=root,
        depth=0,
        tainted_in=Fraction(original_amount),
        first_reached_at=anchor_time,
    )
    result.nodes[root] = root_node

    frontier = [root_node]
    visited: set[str] = set()
    edges_used = 0

    for _depth in range(params.max_depth):
        next_frontier: list[TraceNode] = []
        # Highest attributed value first: if a budget runs out, it runs out on the
        # branches that matter least.
        for node in sorted(frontier, key=lambda n: n.tainted_in, reverse=True):
            if node.address in visited:
                continue
            visited.add(node.address)

            if (
                params.stop_at_services
                and is_service_boundary is not None
                and await is_service_boundary(node.address)
            ):
                # Not a dead end — this is the answer. Downstream of an exchange hot
                # wallet is other customers' money.
                _terminate(node, TerminationReason.SERVICE_BOUNDARY)
                continue

            if result.addresses_fetched >= params.address_budget:
                _terminate(node, TerminationReason.EDGE_BUDGET)
                continue

            transfers = _eligible(await fetch(node.address), params)
            result.addresses_fetched += 1

            flows = _aggregate_outflows(transfers, node, params)
            if not flows:
                # Good news for an investigator: the funds have not moved on.
                _terminate(node, TerminationReason.NO_OUTFLOW)
                continue

            total_in = taint.inbound_total(transfers, node.address)
            total_out = sum(f.total_raw for f in flows)
            ratio = taint.haircut_ratio(node.tainted_in, total_in, total_out)

            edges_used = _expand(result, node, flows, ratio, params, edges_used, next_frontier)

        frontier = next_frontier

    for node in frontier:
        if not node.is_terminal:
            _terminate(node, TerminationReason.MAX_DEPTH)

    result.paths = _rank_paths(result)
    invariants.check(result)
    log.info(
        "traced %s: %d nodes, %d edges, %d fetched, %.1f%% pruned",
        root,
        len(result.nodes),
        len(result.edges),
        result.addresses_fetched,
        result.pruned_share * 100,
    )
    return result


def _terminate(node: TraceNode, reason: TerminationReason) -> None:
    node.is_terminal = True
    node.termination_reason = reason


def _aggregate_outflows(
    transfers: list[NormalizedTransfer], node: TraceNode, params: TraceParams
) -> list[_Flow]:
    """Outbound flows worth following, grouped per counterparty.

    Only transfers *after* the tainted funds arrived are eligible: money that left before
    the victim paid cannot contain the victim's money. Forgetting this condition produces
    a large, plausible-looking false trail.
    """
    flows: dict[tuple[str, str], _Flow] = {}
    for t in transfers:
        if _source(t, params.direction) != node.address:
            continue
        if node.first_reached_at is not None and t.block_time < node.first_reached_at:
            continue
        if t.amount_raw < params.min_amount_raw:
            continue
        counterparty = _target(t, params.direction)
        if counterparty == node.address:  # self-transfer
            continue
        key = (counterparty, t.asset_key)
        flow = flows.get(key)
        if flow is None:
            flow = _Flow(
                counterparty=counterparty,
                asset_key=t.asset_key,
                asset_symbol=t.asset_symbol,
                asset_contract=t.asset_contract,
                decimals=t.decimals,
            )
            flows[key] = flow
        flow.add(t)
    return list(flows.values())


def _expand(
    result: TraceResult,
    node: TraceNode,
    flows: list[_Flow],
    ratio: Fraction,
    params: TraceParams,
    edges_used: int,
    next_frontier: list[TraceNode],
) -> int:
    """Record edges for the flows worth following; record every other flow as pruned."""
    flows.sort(key=lambda f: f.total_raw, reverse=True)
    followed, capped = flows[: params.fanout_cap], flows[params.fanout_cap :]

    for flow in capped:
        _prune(result, node, flow, ratio, PruneReason.FANOUT_CAP)

    threshold = params.taint_threshold * result.original_amount

    for flow in followed:
        attributed = taint.attribute(flow.total_raw, ratio)
        if attributed < threshold:
            _prune(result, node, flow, ratio, PruneReason.BELOW_THRESHOLD)
            continue
        if edges_used >= params.edge_budget:
            _prune(result, node, flow, ratio, TerminationReason.EDGE_BUDGET)
            continue

        assert flow.first_at is not None and flow.last_at is not None
        result.edges.append(
            TraceEdge(
                from_address=node.address,
                to_address=flow.counterparty,
                asset_key=flow.asset_key,
                asset_symbol=flow.asset_symbol,
                asset_contract=flow.asset_contract,
                decimals=flow.decimals,
                total_amount_raw=flow.total_raw,
                tainted_amount=attributed,
                transfer_count=flow.count,
                first_transfer_at=flow.first_at,
                last_transfer_at=flow.last_at,
                tx_hashes=flow.tx_hashes,
            )
        )
        node.attributed_out += attributed
        edges_used += 1

        target = result.nodes.get(flow.counterparty)
        if target is None:
            target = TraceNode(
                address=flow.counterparty,
                depth=node.depth + 1,
                first_reached_at=flow.first_at,
            )
            result.nodes[flow.counterparty] = target
            next_frontier.append(target)
        elif flow.first_at is not None and (
            target.first_reached_at is None or flow.first_at < target.first_reached_at
        ):
            target.first_reached_at = flow.first_at
        # Taint reaching an already-processed address is added but not re-expanded. It
        # becomes retained there — a conservative under-attribution, and what makes a
        # cycle terminate instead of looping.
        target.tainted_in += attributed

    return edges_used


def _prune(result: TraceResult, node: TraceNode, flow: _Flow, ratio: Fraction, reason: str) -> None:
    attributed = taint.attribute(flow.total_raw, ratio)
    result.pruned.append(
        PrunedBranch(
            from_address=node.address,
            to_address=flow.counterparty,
            asset_key=flow.asset_key,
            total_amount_raw=flow.total_raw,
            tainted_amount=attributed,
            reason=str(reason),
        )
    )
    node.pruned_out += attributed


def _rank_paths(result: TraceResult) -> list[TracePath]:
    """Rank root-to-terminal paths by attributed value.

    The graph shows everything; an investigator needs the three paths that carried the
    money. A path ending at an attributed service outranks one that merely ran out of
    depth, because it is actionable.
    """
    parents: dict[str, tuple[str, Fraction, datetime]] = {}
    for edge in sorted(result.edges, key=lambda e: e.tainted_amount, reverse=True):
        parents.setdefault(
            edge.to_address, (edge.from_address, edge.tainted_amount, edge.last_transfer_at)
        )

    paths: list[TracePath] = []
    for terminal in result.terminals:
        if terminal.address == result.root:
            continue
        chain: list[str] = [terminal.address]
        last_activity: datetime | None = None
        cursor = terminal.address
        while cursor in parents and len(chain) <= result.params.max_depth + 1:
            parent, _, seen_at = parents[cursor]
            if last_activity is None or seen_at > last_activity:
                last_activity = seen_at
            chain.append(parent)
            cursor = parent
        chain.reverse()
        paths.append(
            TracePath(
                addresses=chain,
                attributed=terminal.tainted_in,
                terminal_reason=terminal.termination_reason,
                last_activity=last_activity,
            )
        )

    # Attributed value dominates (WALLET_TRACING.md section 8): the path that carried the
    # money is the one to report. Endpoints an investigator can act on — an identified
    # service, or funds that have not moved — get a modest boost, enough to lift a
    # slightly smaller actionable path above a larger dead end, but not enough to let a
    # tiny peel outrank the main flow.
    actionable = {TerminationReason.SERVICE_BOUNDARY, TerminationReason.NO_OUTFLOW}
    boost = Fraction(3, 2)

    def rank(path: TracePath) -> tuple[Fraction, int]:
        weight = boost if path.terminal_reason in actionable else Fraction(1)
        return (path.attributed * weight, -path.hops)

    paths.sort(key=rank, reverse=True)
    return paths
