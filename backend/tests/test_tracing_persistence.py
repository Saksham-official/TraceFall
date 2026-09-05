"""Trace persistence, against the real schema."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun, Trace
from app.db.models.analysis import TraceEdge as TraceEdgeRow
from app.db.models.analysis import TraceNode as TraceNodeRow
from app.db.models.blockchain import Address, Asset, Chain
from app.db.models.case import Case
from app.db.models.enums import AnalysisStatus, ChainCode, TaintModel, TerminationReason
from app.intel import service as intel
from app.tracing import invariants, persistence
from app.tracing.engine import trace
from app.tracing.models import TraceParams, TransfersUnavailable
from tests.conftest import make_user
from tests.tracing_fixtures import USDT, fetcher, services, tx


async def _run(session: AsyncSession) -> tuple[AnalysisRun, int]:
    user = await make_user(session, f"trace-{uuid.uuid4().hex[:6]}@example.gov")
    case = Case(case_number=f"TF-TR-{uuid.uuid4().hex[:6]}", title="Trace", owner_id=user.id)
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    root = Address(chain_id=chain.id, address="SCAM")
    session.add_all([case, root])
    # The traced asset must exist for edges to reference it. `assets` is reference data
    # preserved between tests, so this is an upsert, not an insert.
    asset = await session.scalar(
        select(Asset).where(Asset.chain_id == chain.id, Asset.contract_address == USDT)
    )
    if asset is None:
        session.add(Asset(chain_id=chain.id, contract_address=USDT, symbol="USDT", decimals=6))
    await session.flush()
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=root.id,
        status=AnalysisStatus.RUNNING,
        triggered_by=user.id,
    )
    session.add(run)
    await session.commit()
    return run, chain.id


async def test_a_trace_round_trips_to_the_database(session: AsyncSession) -> None:
    run, _ = await _run(session)
    transfers = [
        tx("VICTIM", "SCAM", 40_000_000_000, 0),
        tx("SCAM", "MULE", 40_000_000_000, 30),
        tx("MULE", "DEPOSIT", 40_000_000_000, 60),
    ]
    asset_key = f"{ChainCode.TRON}:{USDT}"
    result = await trace(
        "SCAM",
        40_000_000_000,
        fetcher(transfers),
        TraceParams(asset_key=asset_key, max_depth=3),
        is_service_boundary=services("DEPOSIT"),
    )

    saved = await persistence.save(session, run, result, ChainCode.TRON)

    assert saved.taint_model is TaintModel.HAIRCUT
    assert saved.node_count == len(result.nodes)
    assert saved.edge_count == len(result.edges)

    nodes = await session.scalar(
        select(func.count()).select_from(TraceNodeRow).where(TraceNodeRow.trace_id == saved.id)
    )
    edges = await session.scalar(
        select(func.count()).select_from(TraceEdgeRow).where(TraceEdgeRow.trace_id == saved.id)
    )
    assert nodes == len(result.nodes)
    assert edges == len(result.edges)


async def test_addresses_discovered_by_the_trace_are_created(session: AsyncSession) -> None:
    run, chain_id = await _run(session)
    transfers = [tx("VICTIM", "SCAM", 1_000, 0), tx("SCAM", "BRAND_NEW", 1_000, 10)]
    result = await trace(
        "SCAM", 1_000, fetcher(transfers), TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}")
    )
    await persistence.save(session, run, result, ChainCode.TRON)

    found = await session.scalar(
        select(Address).where(Address.chain_id == chain_id, Address.address == "BRAND_NEW")
    )
    assert found is not None


async def test_termination_reasons_survive_persistence(session: AsyncSession) -> None:
    """An investigator reads the reason a trace stopped; it must not be lost on the way
    to the database."""
    run, _ = await _run(session)
    transfers = [tx("VICTIM", "SCAM", 1_000, 0), tx("SCAM", "EXCHANGE", 1_000, 10)]
    result = await trace(
        "SCAM",
        1_000,
        fetcher(transfers),
        TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}"),
        is_service_boundary=services("EXCHANGE"),
    )
    saved = await persistence.save(session, run, result, ChainCode.TRON)

    rows = await session.scalars(
        select(TraceNodeRow).where(
            TraceNodeRow.trace_id == saved.id, TraceNodeRow.is_terminal.is_(True)
        )
    )
    reasons = {r.termination_reason for r in rows.all()}
    assert TerminationReason.SERVICE_BOUNDARY in reasons


async def test_edges_keep_the_transaction_hashes_for_drill_down(
    session: AsyncSession,
) -> None:
    """No finding may dead-end without a route back to raw evidence."""
    run, _ = await _run(session)
    transfers = [
        tx("VICTIM", "SCAM", 2_000, 0),
        tx("SCAM", "MULE", 1_000, 10),
        tx("SCAM", "MULE", 1_000, 11),
    ]
    result = await trace(
        "SCAM", 2_000, fetcher(transfers), TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}")
    )
    saved = await persistence.save(session, run, result, ChainCode.TRON)

    edge = await session.scalar(select(TraceEdgeRow).where(TraceEdgeRow.trace_id == saved.id))
    assert edge is not None
    assert edge.transfer_count == 2, "repeated transfers aggregate into one edge"
    assert len(edge.tx_hashes) == 2
    assert edge.tainted_amount_raw == Decimal(2_000)


async def test_loading_transfers_back_from_the_canonical_layer(
    session: AsyncSession,
) -> None:
    """Phase 4 writes transfers; the tracer reads them back through this path."""
    loaded = await intel.load_transfers(session, ChainCode.TRON, ["NOBODY"])
    assert loaded == {"NOBODY": []}


async def test_trace_rows_reference_their_analysis_run(session: AsyncSession) -> None:
    run, _ = await _run(session)
    transfers = [tx("VICTIM", "SCAM", 1_000, 0)]
    result = await trace(
        "SCAM", 1_000, fetcher(transfers), TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}")
    )
    saved = await persistence.save(session, run, result, ChainCode.TRON)
    found = await session.scalar(select(Trace).where(Trace.analysis_run_id == run.id))
    assert found is not None and found.id == saved.id


async def test_a_reloaded_trace_keeps_what_it_did_not_follow(session: AsyncSession) -> None:
    """The graph is rebuilt from these rows, so a pruned branch lost here is lost for good."""
    run, _ = await _run(session)
    transfers = [tx("VICTIM", "SCAM", 1_000_000, 0)] + [
        tx("SCAM", f"OUT{i:02d}", 100_000 - i * 1_000, 10) for i in range(10)
    ]
    result = await trace(
        "SCAM",
        1_000_000,
        fetcher(transfers),
        TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}", fanout_cap=3),
    )
    assert result.pruned, "the fixture must actually prune something"
    await persistence.save(session, run, result, ChainCode.TRON)

    reloaded = await persistence.load(session, run.id)

    assert reloaded is not None
    assert reloaded.root == result.root
    assert len(reloaded.nodes) == len(result.nodes)
    assert len(reloaded.edges) == len(result.edges)
    assert [(b.from_address, b.to_address, b.reason) for b in reloaded.pruned] == [
        (b.from_address, b.to_address, b.reason) for b in result.pruned
    ]
    assert reloaded.total_pruned == result.total_pruned


async def test_the_accounting_invariant_survives_the_round_trip(session: AsyncSession) -> None:
    """If value cannot be re-accounted from stored rows, a report cannot cite it."""
    run, _ = await _run(session)
    transfers = [
        tx("VICTIM", "SCAM", 1_000_000, 0),
        tx("SCAM", "A", 600_000, 10),
        tx("SCAM", "B", 400_000, 10),
    ]
    result = await trace(
        "SCAM", 1_000_000, fetcher(transfers), TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}")
    )
    await persistence.save(session, run, result, ChainCode.TRON)

    reloaded = await persistence.load(session, run.id)

    assert reloaded is not None
    invariants.check(reloaded)
    assert reloaded.original_amount == result.original_amount


async def test_addresses_the_trace_could_not_reach_survive_storage(
    session: AsyncSession,
) -> None:
    run, _ = await _run(session)
    transfers = [tx("VICTIM", "SCAM", 1_000, 0), tx("SCAM", "GONE", 1_000, 10)]

    async def fetch(address: str) -> list:
        if address == "GONE":
            raise TransfersUnavailable(address, "no fixture is committed for this address")
        return [t for t in transfers if address in (t.from_address, t.to_address)]

    result = await trace(
        "SCAM", 1_000, fetch, TraceParams(asset_key=f"{ChainCode.TRON}:{USDT}", max_depth=3)
    )
    await persistence.save(session, run, result, ChainCode.TRON)

    reloaded = await persistence.load(session, run.id)

    assert reloaded is not None
    assert [u["address"] for u in reloaded.unavailable] == ["GONE"]
    assert reloaded.nodes["GONE"].termination_reason is TerminationReason.DATA_UNAVAILABLE
