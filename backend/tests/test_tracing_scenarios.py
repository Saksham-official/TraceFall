"""The named scenarios from docs/TESTING_STRATEGY.md section 4, and one test per
termination reason.

Each is a shape investigators actually meet, expressed as the smallest graph that
produces it.
"""

from fractions import Fraction

from app.chains.base import TimeWindow
from app.db.models.enums import TerminationReason
from app.tracing import invariants
from app.tracing.engine import trace
from app.tracing.models import TraceParams
from tests.tracing_fixtures import ASSET, BASE_TIME, fetcher, services, tx

PARAMS = TraceParams(asset_key=ASSET, max_depth=3, fanout_cap=8)


async def test_simple_two_hop_ends_at_an_exchange() -> None:
    """The shape the product exists to produce: money to a deposit address."""
    transfers = [
        tx("VICTIM", "SCAM", 40_000_000_000, 0),
        tx("SCAM", "MULE", 40_000_000_000, 30),
        tx("MULE", "DEPOSIT", 40_000_000_000, 60),
    ]
    result = await trace(
        "SCAM",
        40_000_000_000,
        fetcher(transfers),
        PARAMS,
        is_service_boundary=services("DEPOSIT"),
    )
    deposit = result.nodes["DEPOSIT"]
    assert deposit.termination_reason is TerminationReason.SERVICE_BOUNDARY
    assert deposit.tainted_in == Fraction(40_000_000_000)
    assert result.paths[0].addresses == ["SCAM", "MULE", "DEPOSIT"]


async def test_fan_out_fifty_follows_the_largest_and_records_the_rest() -> None:
    transfers = [tx("VICTIM", "A", 5_000_000, 0)] + [
        tx("A", f"OUT{i:02d}", 100_000 + i * 1_000, 10) for i in range(50)
    ]
    result = await trace(
        "A", 5_000_000, fetcher(transfers), TraceParams(asset_key=ASSET, fanout_cap=20)
    )
    assert len(result.edges) == 20
    assert len(result.pruned) == 30
    invariants.check(result)


async def test_peel_chain_keeps_the_main_flow_as_the_top_path() -> None:
    """A large amount moves forward while small amounts peel off at every hop."""
    transfers = [tx("VICTIM", "P0", 1_000_000, 0)]
    remaining = 1_000_000
    for i in range(5):
        peel = 20_000
        remaining -= peel
        transfers.append(tx(f"P{i}", f"PEEL{i}", peel, 10 + i))
        transfers.append(tx(f"P{i}", f"P{i + 1}", remaining, 11 + i))
    result = await trace(
        "P0", 1_000_000, fetcher(transfers), TraceParams(asset_key=ASSET, max_depth=5)
    )
    invariants.check(result)
    # The main line, not a peel, carries the most value.
    assert result.paths[0].addresses[-1].startswith("P")
    assert not result.paths[0].addresses[-1].startswith("PEEL")


async def test_cycle_a_b_a_terminates() -> None:
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "B", 100_000, 10),
        tx("B", "A", 100_000, 20),
    ]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    invariants.check(result)
    assert set(result.nodes) == {"A", "B"}


async def test_mixer_terminates_the_trail() -> None:
    """Tornado Cash and its equivalents break the link cryptographically. Stopping is
    the honest answer, not a limitation of the implementation."""
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "MIXER", 100_000, 10),
        tx("MIXER", "ANYONE", 100_000, 20),
    ]
    result = await trace(
        "A", 100_000, fetcher(transfers), PARAMS, is_service_boundary=services("MIXER")
    )
    assert "ANYONE" not in result.nodes
    assert result.nodes["MIXER"].termination_reason is TerminationReason.SERVICE_BOUNDARY


async def test_no_outflow_is_good_news_not_a_failure() -> None:
    """The funds have not moved. These are the recoverable cases."""
    transfers = [tx("VICTIM", "A", 100_000, 0)]
    result = await trace("A", 100_000, fetcher(transfers), PARAMS)
    assert len(result.nodes) == 1
    assert result.nodes["A"].termination_reason is TerminationReason.NO_OUTFLOW
    assert result.nodes["A"].retained == Fraction(100_000)


async def test_dust_flood_is_entirely_pruned_and_still_balances() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [tx("A", f"D{i}", 50, 10) for i in range(1_000)]
    result = await trace("A", 1_000_000, fetcher(transfers), PARAMS)
    assert result.edges == []
    invariants.check(result)


async def test_deep_chain_stops_at_max_depth_and_reports_remaining_value() -> None:
    transfers = [tx("VICTIM", "H0", 900_000, 0)] + [
        tx(f"H{i}", f"H{i + 1}", 900_000, 10 + i) for i in range(12)
    ]
    result = await trace(
        "H0", 900_000, fetcher(transfers), TraceParams(asset_key=ASSET, max_depth=5)
    )
    terminal = result.nodes["H5"]
    assert terminal.termination_reason is TerminationReason.MAX_DEPTH
    assert terminal.tainted_in == Fraction(900_000)


# --- one test per termination reason ---------------------------------------------


async def test_termination_reason_time_window() -> None:
    from datetime import timedelta

    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "LATER", 100_000, 60 * 24 * 40),
    ]
    window = TimeWindow(start=BASE_TIME - timedelta(days=1), end=BASE_TIME + timedelta(days=1))
    result = await trace(
        "A", 100_000, fetcher(transfers), TraceParams(asset_key=ASSET, window=window)
    )
    # Nothing eligible inside the window, so the address has no traceable outflow.
    assert result.nodes["A"].termination_reason is TerminationReason.NO_OUTFLOW
    assert "LATER" not in result.nodes


async def test_every_terminal_node_states_why_it_stopped() -> None:
    transfers = [
        tx("VICTIM", "A", 100_000, 0),
        tx("A", "B", 50_000, 10),
        tx("A", "EXCHANGE", 50_000, 11),
    ]
    result = await trace(
        "A", 100_000, fetcher(transfers), PARAMS, is_service_boundary=services("EXCHANGE")
    )
    for node in result.terminals:
        assert node.termination_reason is not None, f"{node.address} stopped without a reason"


async def test_paths_rank_actionable_endpoints_first() -> None:
    """A path ending at an identified exchange outranks one that merely ran out of depth."""
    transfers = [
        tx("VICTIM", "A", 200_000, 0),
        tx("A", "TO_EXCHANGE", 90_000, 10),
        tx("TO_EXCHANGE", "EXCHANGE", 90_000, 20),
        tx("A", "DEEP0", 110_000, 11),
        tx("DEEP0", "DEEP1", 110_000, 21),
        tx("DEEP1", "DEEP2", 110_000, 31),
    ]
    result = await trace(
        "A",
        200_000,
        fetcher(transfers),
        TraceParams(asset_key=ASSET, max_depth=3),
        is_service_boundary=services("EXCHANGE"),
    )
    top = result.paths[0]
    assert top.terminal_reason is TerminationReason.SERVICE_BOUNDARY
