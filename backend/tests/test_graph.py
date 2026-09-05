"""Graph construction, derived measures, and the render cap.

The graphs here are produced by the real tracing engine rather than hand-assembled, so
what is tested is the object an investigator will actually be shown.
"""

from fractions import Fraction

from app.attribution.decision import AttributionResult
from app.db.models.enums import AttributionMethod, AttributionTier, EntityType
from app.graph import algorithms, builder, serialize
from app.tracing.engine import trace
from app.tracing.models import TraceParams
from tests.tracing_fixtures import ASSET, fetcher, services, tx

PARAMS = TraceParams(asset_key=ASSET, max_depth=3, fanout_cap=8)
AMOUNT = 40_000_000_000


def confirmed_exchange(name: str = "Test Exchange") -> AttributionResult:
    return AttributionResult(
        tier=AttributionTier.CONFIRMED,
        entity_type=EntityType.EXCHANGE,
        method=AttributionMethod.DATASET_MATCH,
        entity_name=name,
        evidence=[{"type": "DATASET_MATCH", "detail": "..."}],
    )


async def two_hop_graph() -> builder.TraceGraph:
    transfers = [
        tx("VICTIM", "SCAM", AMOUNT, 0),
        tx("SCAM", "MULE", AMOUNT, 30),
        tx("MULE", "DEPOSIT", AMOUNT, 60),
    ]
    result = await trace(
        "SCAM", AMOUNT, fetcher(transfers), PARAMS, is_service_boundary=services("DEPOSIT")
    )
    return builder.build(result)


# --- Construction --------------------------------------------------------------------


async def test_the_graph_carries_the_trace_it_came_from() -> None:
    graph = await two_hop_graph()

    assert set(graph.nodes) == {"SCAM", "MULE", "DEPOSIT"}
    assert list(graph.edges) == [("SCAM", "MULE"), ("MULE", "DEPOSIT")]
    assert graph.graph["root"] == "SCAM"
    assert graph.nodes["SCAM"]["is_root"] is True
    assert graph.nodes["DEPOSIT"]["is_terminal"] is True
    assert graph.nodes["DEPOSIT"]["termination_reason"] == "SERVICE_BOUNDARY"
    assert graph.nodes["DEPOSIT"]["taint_share"] == 1.0


async def test_parallel_transfers_aggregate_into_one_edge_keeping_every_hash() -> None:
    """Twenty transfers between two addresses are one edge — that is what makes it legible."""
    transfers = [tx("VICTIM", "A", 20_000, 0)] + [tx("A", "B", 1_000, 10 + i) for i in range(20)]
    result = await trace("A", 20_000, fetcher(transfers), PARAMS)
    graph = builder.build(result)

    edge = graph.edges["A", "B"]
    assert edge["transfer_count"] == 20
    assert len(edge["tx_hashes"]) == 20
    assert edge["total_amount_raw"] == 20_000


async def test_pruned_branches_are_recorded_on_the_node_they_left() -> None:
    """A smaller answer is never shown silently — the UI can say what was not followed."""
    transfers = [tx("VICTIM", "A", 5_000_000, 0)] + [
        tx("A", f"OUT{i:02d}", 100_000 + i * 1_000, 10) for i in range(50)
    ]
    result = await trace(
        "A", 5_000_000, fetcher(transfers), TraceParams(asset_key=ASSET, fanout_cap=5)
    )
    graph = builder.build(result)

    assert graph.nodes["A"]["pruned_branches"]
    assert all(branch["reason"] for branch in graph.nodes["A"]["pruned_branches"])


async def test_attribution_lands_on_the_nodes_as_its_own_attribute() -> None:
    graph = builder.enrich(await two_hop_graph(), {"DEPOSIT": confirmed_exchange()})

    assert graph.nodes["DEPOSIT"]["attribution_tier"] == "CONFIRMED"
    assert graph.nodes["DEPOSIT"]["entity_name"] == "Test Exchange"
    assert builder.service_nodes(graph) == {"DEPOSIT"}
    # A node the attribution stage never saw stays None — not UNATTRIBUTED, which is a
    # finding rather than an absence.
    assert graph.nodes["MULE"]["attribution_tier"] is None


# --- Derived measures ----------------------------------------------------------------


async def test_highest_value_path_is_the_one_that_kept_the_most_value() -> None:
    """Hand-computed: the upper branch retains 90%, the lower 10%."""
    transfers = [
        tx("VICTIM", "A", 1_000_000, 0),
        tx("A", "BIG", 900_000, 10),
        tx("A", "SMALL", 100_000, 10),
        tx("BIG", "BIG_END", 900_000, 20),
        tx("SMALL", "SMALL_END", 100_000, 20),
    ]
    result = await trace("A", 1_000_000, fetcher(transfers), TraceParams(asset_key=ASSET))
    graph = builder.build(result)

    path = algorithms.highest_value_path(graph)

    assert path is not None
    assert path.addresses == ["A", "BIG", "BIG_END"]
    assert path.hops == 2
    assert round(path.retained_share, 4) == 0.9


async def test_highest_value_path_ends_at_a_terminal_not_the_first_hop() -> None:
    graph = await two_hop_graph()

    path = algorithms.highest_value_path(graph)

    assert path is not None
    assert path.addresses == ["SCAM", "MULE", "DEPOSIT"]


async def test_shortest_path_answers_how_two_addresses_connect() -> None:
    graph = await two_hop_graph()

    assert algorithms.shortest_path(graph, "SCAM", "DEPOSIT") == ["SCAM", "MULE", "DEPOSIT"]
    # Direction is the semantic content of this graph; there is no undirected view.
    assert algorithms.shortest_path(graph, "DEPOSIT", "SCAM") is None
    assert algorithms.shortest_path(graph, "SCAM", "NOWHERE") is None


async def test_betweenness_finds_the_chokepoint() -> None:
    """Four branches reconverging on one collection address — the mule that matters."""
    transfers = [tx("VICTIM", "A", 4_000_000, 0)]
    for i in range(4):
        transfers.append(tx("A", f"HOP{i}", 1_000_000, 10))
        transfers.append(tx(f"HOP{i}", "CHOKE", 1_000_000, 20))
    transfers.append(tx("CHOKE", "EXIT", 4_000_000, 30))
    result = await trace("A", 4_000_000, fetcher(transfers), TraceParams(asset_key=ASSET))
    graph = builder.build(result)

    scores = algorithms.betweenness(graph)

    assert max(scores, key=lambda a: scores[a]) == "CHOKE"
    assert scores["CHOKE"] > scores["HOP0"]


async def test_components_separate_paths_that_never_reconverge() -> None:
    graph = await two_hop_graph()

    assert algorithms.components(graph) == [["DEPOSIT", "MULE", "SCAM"]]


async def test_cycles_show_funds_returning() -> None:
    transfers = [
        tx("VICTIM", "A", 1_000_000, 0),
        tx("A", "B", 1_000_000, 10),
        tx("B", "A", 1_000_000, 20),
    ]
    result = await trace("A", 1_000_000, fetcher(transfers), TraceParams(asset_key=ASSET))
    graph = builder.build(result)

    found = algorithms.cycles(graph)

    assert [sorted(cycle) for cycle in found] == [["A", "B"]]


async def test_degrees_feed_the_fan_detectors() -> None:
    graph = await two_hop_graph()

    assert algorithms.degrees(graph)["MULE"] == (1, 1)
    assert algorithms.degrees(graph)["SCAM"] == (0, 1)


async def test_an_edge_that_carried_nothing_is_not_a_route() -> None:
    """A zero-value edge lends no centrality and appears in no path."""
    graph = await two_hop_graph()
    graph.add_edge("SCAM", "GHOST", weight=builder.UNREACHABLE, tainted_amount_raw=0)
    graph.add_node("GHOST", is_terminal=True, tainted_amount_raw=0, taint_share=0.0)

    path = algorithms.highest_value_path(graph)

    assert path is not None
    assert "GHOST" not in path.addresses


# --- The render cap ------------------------------------------------------------------


async def wide_graph(width: int = 60) -> builder.TraceGraph:
    """A fans out to `width` intermediaries that all reconverge on one exit.

    The intermediaries are the nodes a cap is allowed to drop; the root and the exit are
    not. Each carries a different amount so "highest tainted value first" has something
    to order by.
    """
    total = sum(10_000 + i for i in range(width))
    transfers = [tx("VICTIM", "A", total, 0)]
    for i in range(width):
        transfers.append(tx("A", f"OUT{i:03d}", 10_000 + i, 10))
        transfers.append(tx(f"OUT{i:03d}", "EXIT", 10_000 + i, 20))
    result = await trace(
        "A",
        total,
        fetcher(transfers),
        TraceParams(asset_key=ASSET, fanout_cap=width, address_budget=width + 5),
    )
    return builder.build(result)


async def test_the_cap_returns_exactly_max_nodes_and_says_it_truncated() -> None:
    graph = await wide_graph(60)

    payload = serialize.render(graph, max_nodes=20)

    assert payload["node_count"] == 20
    assert payload["truncated"] is True
    assert payload["omitted_node_count"] == graph.number_of_nodes() - 20


async def test_the_cap_never_drops_the_root_a_terminal_or_a_service() -> None:
    graph = builder.enrich(await wide_graph(60), {"OUT007": confirmed_exchange()})

    capped, truncated = serialize.cap(graph, max_nodes=5)

    assert truncated is True
    assert capped.number_of_nodes() == 5
    assert "A" in capped, "the root is the case"
    assert "EXIT" in capped, "a terminal is where the money ended"
    assert "OUT007" in capped, "a confirmed service is the answer"


async def test_the_cap_keeps_the_answer_even_when_it_cannot_keep_the_number() -> None:
    """Every leaf of a pure fan-out is terminal. An over-large graph beats a missing one."""
    transfers = [tx("VICTIM", "A", 600_000, 0)] + [
        tx("A", f"OUT{i:03d}", 10_000, 10) for i in range(60)
    ]
    result = await trace(
        "A",
        600_000,
        fetcher(transfers),
        TraceParams(asset_key=ASSET, fanout_cap=60, address_budget=65),
    )

    capped, truncated = serialize.cap(builder.build(result), max_nodes=5)

    assert truncated is True
    assert capped.number_of_nodes() == 61


async def test_a_capped_node_says_how_many_branches_are_hidden() -> None:
    graph = await wide_graph(60)

    capped, _ = serialize.cap(graph, max_nodes=10)
    payload = serialize.render(graph, max_nodes=10)
    root = next(node for node in payload["nodes"] if node["address"] == "A")

    assert capped.nodes["A"]["omitted_successors"] > 0
    assert root["omitted_successors"] == capped.nodes["A"]["omitted_successors"]


async def test_a_graph_inside_the_cap_is_not_truncated() -> None:
    payload = serialize.render(await two_hop_graph(), max_nodes=500)

    assert payload["truncated"] is False
    assert payload["omitted_node_count"] == 0
    assert payload["node_count"] == 3


async def test_expansion_fetches_the_subtree_behind_the_affordance() -> None:
    graph = await two_hop_graph()

    payload = serialize.expand(graph, "MULE")

    assert payload["root"] == "MULE"
    assert {node["address"] for node in payload["nodes"]} == {"MULE", "DEPOSIT"}


# --- Serialisation -------------------------------------------------------------------


async def test_amounts_serialise_as_strings_so_precision_survives_transport() -> None:
    """A JSON number cannot hold an 18-decimal raw amount exactly. A report can't be wrong."""
    graph = await two_hop_graph()

    payload = serialize.render(graph)
    node = next(n for n in payload["nodes"] if n["address"] == "DEPOSIT")
    edge = payload["edges"][0]

    assert node["tainted_amount_raw"] == str(AMOUNT)
    assert isinstance(edge["total_amount_raw"], str)
    assert isinstance(edge["tainted_amount_raw"], str)


async def test_every_edge_keeps_its_route_back_to_raw_evidence() -> None:
    """No finding may dead-end without a path to the transaction hashes behind it."""
    payload = serialize.render(await two_hop_graph())

    assert all(edge["tx_hashes"] for edge in payload["edges"])


async def test_the_payload_is_json_serialisable() -> None:
    import json

    graph = builder.enrich(await two_hop_graph(), {"DEPOSIT": confirmed_exchange()})

    assert json.loads(json.dumps(serialize.render(graph)))["truncated"] is False


async def test_taint_shares_stay_exact_in_the_trace_even_though_display_rounds() -> None:
    """The graph rounds a share to size a circle; the trace keeps the exact fraction."""
    transfers = [
        tx("VICTIM", "A", 3, 0),
        tx("A", "B", 1, 10),
        tx("A", "C", 2, 10),
    ]
    result = await trace("A", 3, fetcher(transfers), TraceParams(asset_key=ASSET))

    assert result.nodes["B"].tainted_in == Fraction(1)
    assert builder.build(result).nodes["B"]["taint_share"] == 1 / 3
