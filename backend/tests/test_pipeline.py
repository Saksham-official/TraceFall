"""The wired pipeline, end to end, offline.

RETRIEVAL → NORMALIZATION → TRACING → GRAPH → PATTERNS → ATTRIBUTION against the committed
fixture, with no network. What matters here is not that each engine works — that is
covered by their own suites — but that they meet, that every stage records what it did,
and that a stage which cannot complete says so instead of quietly producing less.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.db.models.analysis import AnalysisRun, Trace, TraceNode
from app.db.models.blockchain import Address, Chain, Transfer
from app.db.models.case import Case, CaseAddress
from app.db.models.entity import Attribution
from app.db.models.enums import (
    AddressRole,
    AnalysisStatus,
    ChainCode,
    TerminationReason,
)
from app.db.models.finding import PatternFinding
from app.tracing.models import TransfersUnavailable
from tests.conftest import make_user
from tests.test_normalize import FIXTURED_TRON_ADDRESS


async def queued_run(
    session: AsyncSession,
    reported_amount: Decimal | None = None,
    reported_at: datetime | None = None,
    **params: object,
) -> uuid.UUID:
    """A case, a suspect address, and a QUEUED analysis run — what the API would create."""
    user = await make_user(session, f"pipeline-{uuid.uuid4().hex[:6]}@example.gov")
    case = Case(case_number=f"TF-{uuid.uuid4().hex[:6]}", title="Pipeline", owner_id=user.id)
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    address = await session.scalar(
        select(Address).where(
            Address.chain_id == chain.id, Address.address == FIXTURED_TRON_ADDRESS
        )
    )
    if address is None:
        address = Address(chain_id=chain.id, address=FIXTURED_TRON_ADDRESS)
        session.add(address)
    session.add(case)
    await session.flush()
    session.add(
        CaseAddress(
            case_id=case.id,
            address_id=address.id,
            role=AddressRole.SUSPECT,
            reported_amount=reported_amount,
            reported_at=reported_at,
            added_by=user.id,
        )
    )
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=address.id,
        status=AnalysisStatus.QUEUED,
        triggered_by=user.id,
        params={"max_depth": 2, "time_window_days": 90, **params},
    )
    session.add(run)
    await session.commit()
    return run.id


async def test_the_pipeline_runs_every_stage_offline(session: AsyncSession) -> None:
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    assert run.status in (AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL)
    assert run.progress_pct == 100
    assert run.stage is None
    assert run.completed_at is not None
    # Every stage that ran recorded its version and what it produced.
    for key in ("ingestion", "normalize", "tracing", "graph", "patterns", "attribution"):
        assert key in run.engine_versions, key


async def test_normalized_transfers_and_a_trace_are_stored(session: AsyncSession) -> None:
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    assert await session.scalar(select(func.count()).select_from(Transfer))
    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    assert trace.node_count >= 1
    nodes = (await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))).all()
    assert nodes
    for node in nodes:
        if node.is_terminal:
            assert node.termination_reason is not None, "a terminal node must say why it stopped"


async def test_attribution_runs_over_the_traced_addresses(session: AsyncSession) -> None:
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    rows = (
        await session.scalars(select(Attribution).where(Attribution.analysis_run_id == run_id))
    ).all()
    assert rows
    for row in rows:
        assert row.evidence
        assert row.engine_version


async def test_the_run_records_what_it_could_not_do(session: AsyncSession) -> None:
    """Fixture mode holds one address. Everything past it is a stated gap, not a silence."""
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    summary = run.engine_versions["trace_summary"]
    if summary.get("unavailable"):
        assert run.status is AnalysisStatus.PARTIAL
        assert any(d["stage"] == "TRACING" for d in run.degradations)
        trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
        assert trace is not None
        reasons = await session.scalars(
            select(TraceNode.termination_reason).where(TraceNode.trace_id == trace.id)
        )
        assert TerminationReason.DATA_UNAVAILABLE in set(reasons)


async def test_an_unanchored_run_still_traces(session: AsyncSession) -> None:
    """No reported amount is noisier, not fatal — the fallback is total inbound value."""
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    summary = run.engine_versions["trace_summary"]
    assert summary["anchored"] is False
    assert summary["anchor_reason"] == "NO_AMOUNT_REPORTED"
    assert int(summary["original_amount_raw"]) > 0


async def test_pattern_findings_are_stored_with_their_notes(session: AsyncSession) -> None:
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    for finding in (
        await session.scalars(
            select(PatternFinding).where(PatternFinding.analysis_run_id == run_id)
        )
    ).all():
        assert finding.false_positive_note.strip()
        assert finding.explanation.strip()


async def test_a_degradable_stage_that_fails_does_not_fail_the_run(
    session: AsyncSession, monkeypatch: object
) -> None:
    """An investigator with a trace and no pattern findings still has their answer."""

    async def explode(*args: object, **kwargs: object) -> tuple:
        raise RuntimeError("graph stage is broken")

    monkeypatch.setattr(worker, "_graph_and_patterns", explode)  # type: ignore[attr-defined]
    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    assert run.status is AnalysisStatus.PARTIAL
    assert any("graph stage is broken" in str(d) for d in run.degradations)
    # The trace survived, and so did the stage after the failure.
    assert await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert await session.scalar(
        select(func.count()).select_from(Attribution).where(Attribution.analysis_run_id == run_id)
    )


async def test_an_unfetchable_address_ends_a_branch_honestly(session: AsyncSession) -> None:
    """`DATA_UNAVAILABLE`, never `NO_OUTFLOW` — we did not look, we did not find nothing."""
    from app.tracing.engine import trace
    from app.tracing.models import TraceParams
    from tests.tracing_fixtures import ASSET, tx

    transfers = [tx("VICTIM", "A", 1_000, 0), tx("A", "B", 1_000, 10)]

    async def fetch(address: str) -> list:
        if address == "B":
            raise TransfersUnavailable(address, "no fixture is committed for this address")
        return [t for t in transfers if address in (t.from_address, t.to_address)]

    result = await trace("A", 1_000, fetch, TraceParams(asset_key=ASSET, max_depth=3))

    assert result.nodes["B"].termination_reason is TerminationReason.DATA_UNAVAILABLE
    assert result.unavailable == [
        {"address": "B", "reason": "no fixture is committed for this address"}
    ]


async def test_a_genuinely_quiet_address_still_reports_no_outflow(session: AsyncSession) -> None:
    """The paired case: an empty answer we *did* earn keeps its stronger reason."""
    from app.tracing.engine import trace
    from app.tracing.models import TraceParams
    from tests.tracing_fixtures import ASSET, tx

    transfers = [tx("VICTIM", "A", 1_000, 0), tx("A", "B", 1_000, 10)]

    async def fetch(address: str) -> list:
        return [t for t in transfers if address in (t.from_address, t.to_address)]

    result = await trace("A", 1_000, fetch, TraceParams(asset_key=ASSET, max_depth=3))

    assert result.nodes["B"].termination_reason is TerminationReason.NO_OUTFLOW
    assert result.unavailable == []


async def test_rerunning_the_pipeline_is_safe(session: AsyncSession) -> None:
    """Re-ingestion is a no-op, and a second run is a second set of findings (FR-124)."""
    first = await queued_run(session)
    await worker._run_pipeline(first)
    transfers_after_first = await session.scalar(select(func.count()).select_from(Transfer))

    second = await queued_run(session)
    await worker._run_pipeline(second)

    assert await session.scalar(select(func.count()).select_from(Transfer)) == transfers_after_first
    assert await session.scalar(select(func.count()).select_from(Trace)) == 2


async def test_a_branch_the_fixtures_cannot_reach_is_reported_not_hidden(
    session: AsyncSession,
) -> None:
    """The multi-hop case in fixture mode: hop two has no fixture, and the run says so.

    This is the whole point of ADR-019. The node must not read as "the funds stopped
    here" when what actually happened is that we could not look.
    """
    from app.chains.tron import adapter as tron
    from app.normalize import service as normalize
    from tests.tracing_fixtures import tx

    next_hop = tron.from_hex("41" + f"{777:040x}")
    senders = [tron.from_hex("41" + f"{800 + i:040x}") for i in range(3)]
    seeded = [
        tx(sender, FIXTURED_TRON_ADDRESS, 1_000_000, i * 10) for i, sender in enumerate(senders)
    ]
    seeded += [tx(FIXTURED_TRON_ADDRESS, next_hop, 1_000_000, 30 + i * 10) for i in range(3)]
    await normalize.persist(session, ChainCode.TRON, seeded)

    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    summary = run.engine_versions["trace_summary"]
    assert summary["nodes"] == 2, "the trace followed the seeded hop"
    assert [u["address"] for u in summary["unavailable"]] == [next_hop]
    assert "no fixture" in summary["unavailable"][0]["reason"]

    # Stated at every level: the run is PARTIAL, the degradation names the stage, and the
    # node carries the honest reason rather than the stronger NO_OUTFLOW claim.
    assert run.status is AnalysisStatus.PARTIAL
    assert any(d["stage"] == "TRACING" for d in run.degradations)
    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    reasons = {
        node.termination_reason
        for node in (
            await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))
        ).all()
    }
    assert TerminationReason.DATA_UNAVAILABLE in reasons
    assert TerminationReason.NO_OUTFLOW not in reasons


async def test_the_risk_stage_scores_and_stores(session: AsyncSession) -> None:
    from app.db.models.finding import RiskAssessment

    run_id = await queued_run(session)

    await worker._run_pipeline(run_id)

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    assert "risk" in run.engine_versions
    assert run.engine_versions["risk_summary"]["config_version"]

    rows = (
        await session.scalars(
            select(RiskAssessment).where(RiskAssessment.analysis_run_id == run_id)
        )
    ).all()
    assert rows
    for row in rows:
        assert 0 <= row.score <= 100
        # The breakdown is the point; a score without it is useless when questioned.
        assert row.signals
        assert row.config_version and row.engine_version
        assert 0 < float(row.confidence) <= 1


async def test_every_stored_score_can_be_added_up_by_hand(session: AsyncSession) -> None:
    """An investigator must be able to check the arithmetic themselves."""
    from app.db.models.finding import RiskAssessment

    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)

    for row in (
        await session.scalars(
            select(RiskAssessment).where(RiskAssessment.analysis_run_id == run_id)
        )
    ).all():
        total = sum(signal["points"] for signal in row.signals)
        assert row.score == min(100, round(total))
        for signal in row.signals:
            assert signal["points"] <= signal["weight"]
            assert signal["description"].strip()
