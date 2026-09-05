"""The five correctness properties of the tracing engine.

docs/WALLET_TRACING.md section 10. A violation here means a wrong number in a police
report, so these run as property tests over generated graphs rather than single examples.
"""

from fractions import Fraction

import pytest

from app.db.models.enums import TerminationReason
from app.tracing import invariants
from app.tracing.engine import trace
from app.tracing.models import TraceParams
from tests.tracing_fixtures import ASSET, fetcher, services, tx

PARAMS = TraceParams(asset_key=ASSET, max_depth=3, fanout_cap=8)


async def test_conservation_no_node_attributes_more_than_it_received() -> None:
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "B", 60_000, 10),
        tx("A", "C", 40_000, 12),
        tx("B", "D", 60_000, 20),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    for node in result.nodes.values():
        assert node.attributed_out + node.pruned_out <= node.tainted_in


async def test_full_accounting_every_unit_is_attributed_pruned_or_retained() -> None:
    """The single best check that the engine is correct."""
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "B", 30_000, 10),
        tx("A", "C", 20_000, 11),
        tx("B", "D", 30_000, 20),
        tx("C", "E", 20_000, 21),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    assert result.total_retained + result.total_pruned == result.original_amount
    invariants.check(result)  # also asserted inside trace(), belt and braces


async def test_determinism_identical_input_gives_identical_output() -> None:
    transfers = [tx("VICTIM", "A", 100_000, 0)] + [
        tx("A", f"OUT{i}", 5_000, 10 + i) for i in range(20)
    ]
    first = await trace("A", 100_000, fetcher(transfers), PARAMS)
    second = await trace("A", 100_000, fetcher(transfers), PARAMS)

    assert [(e.from_address, e.to_address, e.tainted_amount) for e in first.edges] == [
        (e.from_address, e.to_address, e.tainted_amount) for e in second.edges
    ]
    assert first.total_pruned == second.total_pruned
    assert sorted(first.nodes) == sorted(second.nodes)


async def test_termination_a_cycle_does_not_loop_or_inflate_taint() -> None:
    """A to B to A. The classic way a naive tracer hangs or invents money."""
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "B", 100_000, 10),
        tx("B", "A", 100_000, 20),
        tx("A", "B", 100_000, 30),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    invariants.check(result)
    assert result.total_retained + result.total_pruned == Fraction(100_000)
    assert all(n.tainted_in <= result.original_amount * 2 for n in result.nodes.values())


async def test_self_transfers_are_ignored() -> None:
    transfers = [tx("VICTIM", "A", 100_000, 0), tx("A", "A", 100_000, 10)]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    assert result.edges == []
    assert result.nodes["A"].termination_reason is TerminationReason.NO_OUTFLOW


@pytest.mark.parametrize("width", [1, 5, 50, 200])
async def test_termination_on_graphs_of_any_width(width: int) -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"OUT{i}", 1_000_000 // width, 10) for i in range(width)
    ]
    result = await trace("A", 1_000_000, fetcher(transfers), PARAMS)
    invariants.check(result)
    assert len(result.edges) <= PARAMS.fanout_cap


async def test_accounting_holds_when_everything_is_pruned() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"DUST{i}", 100, 10) for i in range(1000)
    ]
    result = await trace("A", 1_000_000, fetcher(transfers), PARAMS)
    invariants.check(result)
    assert result.edges == []
    assert result.total_pruned + result.total_retained == Fraction(1_000_000)


async def test_service_boundary_stops_expansion() -> None:
    """Downstream of an exchange hot wallet is other customers' money."""
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "EXCHANGE", 100_000, 10),
        tx("EXCHANGE", "CUSTOMER", 100_000, 20),
    ]
    result = await trace(
        "A", 100_000, fetcher(transfers), PARAMS, is_service_boundary=services("EXCHANGE")
    )
    assert "CUSTOMER" not in result.nodes, "tracing past a hot wallet implicates innocents"
    assert result.nodes["EXCHANGE"].termination_reason is TerminationReason.SERVICE_BOUNDARY
