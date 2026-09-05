"""Derived measures over the trace graph.

Every function here answers a question an investigator actually asks. Techniques that do
not — PageRank, embeddings, link prediction, max-flow — are rejected in
GRAPH_ANALYTICS.md section 4, and being able to say why is worth more than shipping them.

Nothing here is a bottleneck: at the 5,000-edge ceiling all of it runs in well under the
budgets in section 6, against a retrieval stage measured in tens of seconds.
"""

from dataclasses import dataclass

import networkx as nx

from app.graph.builder import UNREACHABLE, TraceGraph

# Cycles longer than this are not an obfuscation pattern anyone reads; the bound also
# keeps enumeration from exploding on a dense graph.
MAX_CYCLE_LENGTH = 8


@dataclass(frozen=True)
class ValuePath:
    """A path through the graph and the share of the victim's value it carried."""

    addresses: list[str]
    retained_share: float
    tainted_amount_raw: int

    @property
    def hops(self) -> int:
        return len(self.addresses) - 1


def highest_value_path(graph: TraceGraph, root: str | None = None) -> ValuePath | None:
    """The main flow — the path that carried most of the victim's money.

    Shortest path under `weight = -log(taint carried)`, so minimising the sum maximises
    the product of retained taint. The destination is a terminal node: every prefix of a
    path retains at least as much as the path itself, so without fixing the endpoint the
    "best" path would always be the first hop.
    """
    root = root or graph.graph.get("root")
    if root is None or root not in graph:
        return None

    usable = _usable_subgraph(graph)
    if root not in usable:
        return None

    distances, paths = nx.single_source_dijkstra(usable, root, weight="weight")
    assert isinstance(distances, dict) and isinstance(paths, dict)
    candidates = [
        address
        for address in distances
        if address != root and graph.nodes[address].get("is_terminal")
    ]
    if not candidates:
        # A trace with no terminal yet — fall back to whatever the value reached.
        candidates = [address for address in distances if address != root]
    if not candidates:
        return None

    best = min(
        candidates,
        key=lambda a: (distances[a], -graph.nodes[a].get("tainted_amount_raw", 0), a),
    )
    return ValuePath(
        addresses=list(paths[best]),
        retained_share=graph.nodes[best].get("taint_share", 0.0),
        tainted_amount_raw=graph.nodes[best].get("tainted_amount_raw", 0),
    )


def shortest_path(graph: TraceGraph, source: str, target: str) -> list[str] | None:
    """How are these two addresses connected? Fewest hops, direction respected."""
    if source not in graph or target not in graph:
        return None
    try:
        return list(nx.shortest_path(graph, source, target))
    except nx.NetworkXNoPath:
        return None


def betweenness(graph: TraceGraph) -> dict[str, float]:
    """Where is the chokepoint? (FR-94)

    The highest-value derived measure here and the least obvious one. A scammer can
    generate unlimited fresh addresses, but the operation still funnels through a few
    collection points — those are the addresses worth naming in a report and correlating
    across cases.

    Computed over the tainted subgraph, using the same -log weight as a distance, so
    "most traced value passes through here" is what is actually measured.
    """
    usable = _usable_subgraph(graph)
    if usable.number_of_nodes() < 3:
        return dict.fromkeys(graph.nodes, 0.0)
    scores: dict[str, float] = nx.betweenness_centrality(usable, weight="weight", normalized=True)
    return {address: scores.get(address, 0.0) for address in graph.nodes}


def components(graph: TraceGraph) -> list[list[str]]:
    """Is this one operation or several? Distinct paths that never reconverge (FR-95)."""
    return [sorted(component) for component in nx.weakly_connected_components(graph)]


def cycles(graph: TraceGraph, max_length: int = MAX_CYCLE_LENGTH) -> list[list[str]]:
    """Did funds return? Wash activity, or a self-transfer obfuscation attempt."""
    return [cycle for cycle in nx.simple_cycles(graph, length_bound=max_length)]


def degrees(graph: TraceGraph) -> dict[str, tuple[int, int]]:
    """In and out degree per address — feeds fan-in / fan-out detection."""
    return {address: (graph.in_degree(address), graph.out_degree(address)) for address in graph}


def _usable_subgraph(graph: TraceGraph) -> TraceGraph:
    """Edges that actually carried tainted value.

    An edge carrying nothing is not a route the money took, so it must not appear in a
    path or lend a node any centrality.
    """
    carrying: list[tuple[str, str]] = [
        (source, target)
        for source, target in graph.edges
        if graph.edges[source, target].get("weight", UNREACHABLE) < UNREACHABLE
    ]
    subgraph: TraceGraph = graph.edge_subgraph(carrying).copy()
    return subgraph
