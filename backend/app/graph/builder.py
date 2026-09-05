"""Trace to graph.

The trace answers "where did the money go". The graph is the object an investigator
reasons with: nodes they click, edges they follow back to transaction hashes, and the
shape of the flow at a glance.

**A `DiGraph`, not a `MultiDiGraph`.** A trace follows one asset (ADR-017), so there is at
most one aggregated edge per address pair and the multi-edge machinery would buy nothing
while complicating every algorithm that runs over it.

**Edges are already aggregated by the tracing engine** — twenty transfers from A to B are
one edge carrying `transfer_count: 20` and all twenty hashes. That aggregation is what
makes a 3,000-transfer scam wallet legible instead of a hairball, and `tx_hashes` is what
keeps every finding one click from its raw evidence.
"""

import math
from fractions import Fraction
from typing import TYPE_CHECKING

import networkx as nx

from app.attribution.decision import AttributionResult
from app.db.models.enums import AttributionTier
from app.tracing.models import TraceResult

# Weight for the highest-value path: -log of the taint fraction an edge carries onward, so
# the *shortest* path by this weight is the one that retained the most of the victim's
# money. Edges carrying nothing are unusable as a path — log(0) is undefined, and a path
# through them carried no value by definition.
UNREACHABLE = math.inf

# Nodes are addresses. Naming the alias once keeps every signature in the package honest
# about that. NetworkX's classes are generic to the type checker but not at runtime, so
# the subscript has to stay behind TYPE_CHECKING.
if TYPE_CHECKING:
    TraceGraph = nx.DiGraph[str]
else:
    TraceGraph = nx.DiGraph


def build(trace: TraceResult) -> TraceGraph:
    """One node per address, one edge per address pair, all trace metadata attached."""
    graph: TraceGraph = nx.DiGraph(
        root=trace.root,
        anchor_tx_hash=trace.anchor_tx_hash,
        original_amount_raw=str(int(trace.original_amount)),
        asset_key=trace.params.asset_key,
    )

    for address, node in trace.nodes.items():
        graph.add_node(
            address,
            address=address,
            depth=node.depth,
            taint_share=_share(node.tainted_in, trace.original_amount),
            tainted_amount_raw=node.tainted_raw,
            retained_raw=int(node.retained),
            is_terminal=node.is_terminal,
            termination_reason=(str(node.termination_reason) if node.termination_reason else None),
            is_root=address == trace.root,
            first_reached_at=node.first_reached_at,
            # Filled in by `enrich` once attribution has run. Absent is not UNATTRIBUTED:
            # one means the stage did not run, the other is a finding.
            attribution_tier=None,
            entity_name=None,
            entity_type=None,
        )

    for edge in trace.edges:
        source = trace.nodes.get(edge.from_address)
        carried = (
            Fraction(edge.tainted_amount, source.tainted_in)
            if source is not None and source.tainted_in > 0
            else Fraction(0)
        )
        graph.add_edge(
            edge.from_address,
            edge.to_address,
            asset_key=edge.asset_key,
            asset_symbol=edge.asset_symbol,
            decimals=edge.decimals,
            total_amount_raw=edge.total_amount_raw,
            tainted_amount_raw=edge.tainted_raw,
            taint_carried=carried,
            weight=_weight(carried),
            transfer_count=edge.transfer_count,
            first_transfer_at=edge.first_transfer_at,
            last_transfer_at=edge.last_transfer_at,
            tx_hashes=list(edge.tx_hashes),
        )

    # Pruned branches are recorded on the node they left from, so the UI can say "8 more
    # branches, below the taint threshold" rather than quietly showing a smaller answer.
    for branch in trace.pruned:
        if branch.from_address in graph:
            graph.nodes[branch.from_address].setdefault("pruned_branches", []).append(
                {
                    "to": branch.to_address,
                    "reason": branch.reason,
                    "tainted_amount_raw": branch.tainted_raw,
                }
            )
    return graph


def enrich(graph: TraceGraph, attributions: dict[str, AttributionResult]) -> TraceGraph:
    """Attach attribution to the nodes. Mutates and returns the same graph.

    The tier is carried through as its own attribute rather than folded into a label,
    because the UI encodes it as border style: colour is already carrying risk band, and
    this distinction is too important to lose to a projector's colour rendering (NFR-18).
    """
    for address, result in attributions.items():
        if address not in graph:
            continue
        graph.nodes[address].update(
            attribution_tier=str(result.tier),
            entity_name=result.entity_name,
            entity_type=str(result.entity_type),
            attribution_confidence=(
                float(result.confidence) if result.confidence is not None else None
            ),
            is_service=result.is_service,
        )
    return graph


def service_nodes(graph: TraceGraph) -> set[str]:
    """Confirmed services. The cap must never drop one — they are the answer."""
    return {
        address
        for address, data in graph.nodes(data=True)
        if data.get("attribution_tier") == str(AttributionTier.CONFIRMED) and data.get("is_service")
    }


def _share(tainted: Fraction, original: Fraction) -> float:
    """Display only. The exact ratio stays in the trace; this sizes a circle."""
    return float(tainted / original) if original else 0.0


def _weight(carried: Fraction) -> float:
    if carried <= 0:
        return UNREACHABLE
    return -math.log(float(carried))
