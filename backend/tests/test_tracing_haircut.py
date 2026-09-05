"""Haircut arithmetic and the traversal bounds.

The worked examples in docs/WALLET_TRACING.md sections 1 and 3, asserted exactly.
"""

from fractions import Fraction

from app.db.models.enums import TerminationReason
from app.tracing.engine import trace
from app.tracing.models import PruneReason, TraceParams
from tests.tracing_fixtures import ASSET, fetcher, tx

PARAMS = TraceParams(asset_key=ASSET, max_depth=3, fanout_cap=8)


async def test_half_tainted_balance_attributes_half_the_outflow() -> None:
    """100 untainted plus 100 tainted, sends 100 onward: 50 is attributed."""
    transfers = [
        tx("OTHER", "A", 100, 0),
        tx("VICTIM", "A", 100, 1),
        tx("A", "B", 100, 10),
    ]
    result = await trace("A", 100, fetcher(transfers), PARAMS)
    edge = next(e for e in result.edges if e.to_address == "B")
    assert edge.tainted_amount == Fraction(50)
    assert edge.total_amount_raw == 100


async def test_wholly_tainted_balance_attributes_everything() -> None:
    transfers = [tx("VICTIM", "A", 100, 0), tx("A", "B", 100, 10)]
    result = await trace("A", 100, fetcher(transfers), PARAMS)
    assert result.edges[0].tainted_amount == Fraction(100)


async def test_dilution_reduces_what_each_branch_carries() -> None:
    """1,000 tainted into 999,000 untainted: each outflow carries 0.1% of its face value."""
    transfers = [
        tx("OTHER", "A", 999_000, 0),
        tx("VICTIM", "A", 1_000, 1),
        tx("A", "B", 1_000_000, 10),
    ]
    result = await trace("A", 1_000, fetcher(transfers), PARAMS)
    edge = result.edges[0]
    assert edge.total_amount_raw == 1_000_000
    # The whole victim amount is still accounted for; it is just heavily diluted.
    assert edge.tainted_amount == Fraction(1_000)


async def test_branch_below_one_percent_of_the_original_is_pruned() -> None:
    """The threshold is a share of the victim's money, not of the flow it rides on."""
    transfers = [
        tx("OTHER", "A", 999_000, 0),
        tx("VICTIM", "A", 1_000, 1),
        tx("A", "BIG", 900_000, 10),
        tx("A", "TINY", 5_000, 11),
    ]
    result = await trace("A", 1_000, fetcher(transfers), PARAMS)
    # TINY carries 5,000 * 0.001 = 5, under the 10 threshold (1% of 1,000).
    assert {e.to_address for e in result.edges} == {"BIG"}
    pruned = next(p for p in result.pruned if p.to_address == "TINY")
    assert pruned.reason == PruneReason.BELOW_THRESHOLD
    assert pruned.tainted_amount == Fraction(5)


async def test_attribution_never_exceeds_what_actually_moved() -> None:
    """Claiming more taint than ever arrived would let the trace create value.

    Here the claimed original dwarfs the observed flow, which is what happens when an
    address's earlier history falls outside the window.
    """
    transfers = [tx("VICTIM", "A", 100, 0), tx("A", "B", 100, 10)]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    moved = sum((e.tainted_amount for e in result.edges), Fraction(0))
    moved += sum((p.tainted_amount for p in result.pruned), Fraction(0))
    assert moved <= Fraction(100)


async def test_outflow_larger_than_observed_inflow_is_capped() -> None:
    """A wallet may hold a balance from before the victim paid. Dividing by inflow alone
    would attribute more tainted value than ever arrived."""
    transfers = [tx("VICTIM", "A", 1_000, 0), tx("A", "B", 50_000, 10)]
    result = await trace("A", 1_000, fetcher(transfers), PARAMS)
    assert result.edges[0].tainted_amount == Fraction(1_000)
    assert result.nodes["B"].tainted_in == Fraction(1_000)


async def test_outflows_before_the_tainted_inflow_are_not_followed() -> None:
    """Money that left before the victim paid cannot contain the victim's money.

    Forgetting this produces a large, plausible-looking false trail.
    """
    transfers = [
        tx("A", "EARLIER", 100_000, 0),
        tx("VICTIM", "A", 100_000, 60),
        tx("A", "LATER", 100_000, 70),
    ]
    result = await trace(
        "A",
        100_000,
        fetcher(transfers),
        PARAMS,
        anchor_time=transfers[1].block_time,
    )
    assert {e.to_address for e in result.edges} == {"LATER"}


async def test_failed_transfers_are_retained_but_never_traced() -> None:
    from app.db.models.enums import TransferStatus

    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "FAILED_DEST", 100_000, 10, status=TransferStatus.FAILED),
        tx("A", "REAL_DEST", 100_000, 11),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    assert {e.to_address for e in result.edges} == {"REAL_DEST"}


async def test_transfers_of_another_asset_are_not_traced() -> None:
    """Raw amounts across assets are not comparable numbers; pooling them would give a
    confident, meaningless answer."""
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "USDT_DEST", 100_000, 10),
        tx("A", "TRX_DEST", 5_000_000, 11, contract=None),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    assert {e.to_address for e in result.edges} == {"USDT_DEST"}


# --- traversal bounds ------------------------------------------------------------


async def test_depth_limit_is_respected() -> None:
    transfers = [tx("VICTIM", "H0", 100_000, 0)] + [
        tx(f"H{i}", f"H{i + 1}", 100_000, 10 + i) for i in range(10)
    ]
    result = await trace(
        "H0", 100_000, fetcher(transfers), TraceParams(asset_key=ASSET, max_depth=3)
    )
    assert max(n.depth for n in result.nodes.values()) == 3
    assert result.nodes["H3"].termination_reason is TerminationReason.MAX_DEPTH


async def test_fanout_cap_follows_the_largest_and_records_the_rest() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"OUT{i:03d}", 1_000 * (i + 1), 10) for i in range(100)
    ]
    result = await trace(
        "A", 1_000_000, fetcher(transfers), TraceParams(asset_key=ASSET, fanout_cap=20)
    )
    assert len(result.edges) == 20
    capped = [p for p in result.pruned if p.reason == PruneReason.FANOUT_CAP]
    assert len(capped) == 80
    # The 20 largest were followed, not an arbitrary 20.
    followed = {e.to_address for e in result.edges}
    assert "OUT099" in followed and "OUT000" not in followed


async def test_edge_budget_terminates_cleanly() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"OUT{i}", 100_000, 10) for i in range(10)
    ]
    result = await trace(
        "A",
        1_000_000,
        fetcher(transfers),
        TraceParams(asset_key=ASSET, fanout_cap=10, edge_budget=3),
    )
    assert len(result.edges) == 3
    assert any(p.reason == str(TerminationReason.EDGE_BUDGET) for p in result.pruned)


async def test_address_budget_bounds_how_much_is_fetched() -> None:
    transfers = [tx("VICTIM", "H0", 1_000_000, 0)] + [
        tx(f"H{i}", f"H{i + 1}", 1_000_000, 10 + i) for i in range(20)
    ]
    result = await trace(
        "H0",
        1_000_000,
        fetcher(transfers),
        TraceParams(asset_key=ASSET, max_depth=10, address_budget=3),
    )
    assert result.addresses_fetched <= 3


async def test_time_window_excludes_transfers_outside_it() -> None:
    from datetime import timedelta

    from app.chains.base import TimeWindow
    from tests.tracing_fixtures import BASE_TIME

    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "INSIDE", 50_000, 10),
        tx("A", "OUTSIDE", 50_000, 60 * 24 * 40),
    ]
    window = TimeWindow(start=BASE_TIME - timedelta(days=1), end=BASE_TIME + timedelta(days=1))
    result = await trace(
        "A", 100_000, fetcher(transfers), TraceParams(asset_key=ASSET, window=window)
    )
    assert {e.to_address for e in result.edges} == {"INSIDE"}


async def test_pruned_share_is_reported_to_the_investigator() -> None:
    """An investigator must be able to see what the algorithm chose not to look at."""
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"OUT{i}", 10_000, 10) for i in range(100)
    ]
    result = await trace(
        "A", 1_000_000, fetcher(transfers), TraceParams(asset_key=ASSET, fanout_cap=5)
    )
    assert 0 < result.pruned_share < 1
    assert len(result.pruned) == 95
