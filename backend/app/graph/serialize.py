"""Render payload: cap, then serialise.

**Capping must never hide the answer.** Beyond a few hundred nodes human comprehension
fails before the browser does, so the graph is capped — but the root, every terminal, and
every confirmed service node are retained unconditionally, because those are the nodes the
investigator came for. Everything else competes on tainted value.

**`truncated` is always returned and always displayed.** Silently showing an investigator
half of a fund flow is the failure this whole product exists to avoid.
"""

from datetime import datetime
from typing import Any

import networkx as nx

from app.graph import builder
from app.graph.builder import TraceGraph

DEFAULT_MAX_NODES = 500


def cap(graph: TraceGraph, max_nodes: int = DEFAULT_MAX_NODES) -> tuple[TraceGraph, bool]:
    """Reduce to `max_nodes`, keeping what an investigator cannot do without.

    Returns the capped graph and whether anything was dropped. If the nodes that must be
    kept already exceed the cap, they are all kept anyway: an over-large graph is a better
    failure than a graph missing its answer.
    """
    if graph.number_of_nodes() <= max_nodes:
        return graph, False

    root: str | None = graph.graph.get("root")
    mandatory: set[str] = {
        address for address in graph.nodes if graph.nodes[address].get("is_terminal")
    }
    mandatory |= builder.service_nodes(graph)
    if root is not None and root in graph:
        mandatory.add(root)

    optional = sorted(
        (address for address in graph.nodes if address not in mandatory),
        key=lambda a: (-graph.nodes[a].get("tainted_amount_raw", 0), a),
    )
    keep = set(mandatory) | set(optional[: max(0, max_nodes - len(mandatory))])
    capped: TraceGraph = graph.subgraph(keep).copy()
    capped.graph.update(graph.graph)
    # `truncated` means nodes were actually dropped, not merely that a cap was applied.
    # A graph whose mandatory nodes happen to fill the cap loses nothing, and raising a
    # false alarm teaches investigators to ignore the flag that matters.
    truncated = capped.number_of_nodes() < graph.number_of_nodes()

    # Each surviving node records what was cut from under it, so the UI can offer the
    # "+N more" affordance rather than pretending the branch ended.
    for address in capped.nodes:
        omitted = [target for target in graph.successors(address) if target not in keep]
        if omitted:
            capped.nodes[address]["omitted_successors"] = len(omitted)
    return capped, truncated


def render(graph: TraceGraph, max_nodes: int = DEFAULT_MAX_NODES) -> dict[str, Any]:
    """The JSON the frontend draws, and the report embeds."""
    capped, truncated = cap(graph, max_nodes)
    return {
        "root": graph.graph.get("root"),
        "anchor_tx_hash": graph.graph.get("anchor_tx_hash"),
        "asset_key": graph.graph.get("asset_key"),
        "node_count": capped.number_of_nodes(),
        "edge_count": capped.number_of_edges(),
        "truncated": truncated,
        "omitted_node_count": graph.number_of_nodes() - capped.number_of_nodes(),
        "nodes": [_node(address, capped.nodes[address]) for address in sorted(capped.nodes)],
        "edges": [
            _edge(source, target, capped.edges[source, target])
            for source, target in sorted(capped.edges)
        ],
    }


def expand(graph: TraceGraph, address: str, max_nodes: int = DEFAULT_MAX_NODES) -> dict[str, Any]:
    """One capped node's subtree, fetched on demand behind the "+N more" affordance."""
    if address not in graph:
        return {"root": address, "nodes": [], "edges": [], "truncated": False}
    reachable = nx.descendants(graph, address) | {address}
    subtree: TraceGraph = graph.subgraph(reachable).copy()
    subtree.graph.update(graph.graph, root=address)
    return render(subtree, max_nodes)


def _node(address: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": address,
        "depth": data.get("depth"),
        "taint_share": data.get("taint_share"),
        # Raw amounts are strings: they exceed what JSON numbers hold exactly, and an
        # amount that loses precision in transport is a wrong number in a police report.
        "tainted_amount_raw": str(data.get("tainted_amount_raw", 0)),
        "is_root": data.get("is_root", False),
        "is_terminal": data.get("is_terminal", False),
        "termination_reason": data.get("termination_reason"),
        "attribution_tier": data.get("attribution_tier"),
        "entity_name": data.get("entity_name"),
        "entity_type": data.get("entity_type"),
        "attribution_confidence": data.get("attribution_confidence"),
        "first_reached_at": _time(data.get("first_reached_at")),
        "omitted_successors": data.get("omitted_successors", 0),
        "pruned_branches": [
            {**branch, "tainted_amount_raw": str(branch["tainted_amount_raw"])}
            for branch in data.get("pruned_branches", [])
        ],
    }


def _edge(source: str, target: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "asset_symbol": data.get("asset_symbol"),
        "decimals": data.get("decimals"),
        "total_amount_raw": str(data.get("total_amount_raw", 0)),
        "tainted_amount_raw": str(data.get("tainted_amount_raw", 0)),
        "transfer_count": data.get("transfer_count", 0),
        "first_transfer_at": _time(data.get("first_transfer_at")),
        "last_transfer_at": _time(data.get("last_transfer_at")),
        "tx_hashes": data.get("tx_hashes", []),
    }


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
