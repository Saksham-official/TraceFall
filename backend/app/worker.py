"""Analysis queue worker.

Runs the analysis pipeline stage by stage: RETRIEVAL, NORMALIZATION, TRACING, GRAPH,
PATTERNS, ATTRIBUTION, RISK. Each stage declares whether it is required or degradable — a
degradable stage that fails records why and lets the run continue as PARTIAL, because a
partial answer with its limits stated is worth more than no answer.

**Retrieval happens twice, deliberately.** The root address is fetched up front; every
address the trace then discovers is fetched on demand through the engine's callback. The
engine itself stays pure and network-free — it asks for transfers and gets them, or gets
`TransfersUnavailable`, which ends that branch as `DATA_UNAVAILABLE` rather than as the
much stronger claim that the funds stopped there (ADR-019).
"""

import asyncio
import contextlib
import logging
import sys
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attribution import engine as attribution
from app.attribution.decision import ENGINE_VERSION as ATTRIBUTION_VERSION
from app.chains.base import TimeWindow
from app.core.logging import configure_logging
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address, Chain
from app.db.models.case import CaseAddress
from app.db.models.enums import AnalysisStage, AnalysisStatus, ChainCode
from app.db.session import SessionFactory
from app.graph import builder
from app.ingestion import service
from app.ingestion.fixtures import FixtureMissing
from app.ingestion.service import AddressData
from app.intel import features as intel_features
from app.intel import service as intel
from app.normalize import service as normalize
from app.normalize.transfer import NormalizedTransfer
from app.orchestrator import queue

# Imported for its side effect as well as its name: importing the package registers
# every detector (see app/patterns/__init__.py).
from app.patterns import detectors as _detectors  # noqa: F401
from app.patterns import persistence as pattern_store
from app.patterns.base import DETECTOR_VERSION, Subject, run_all
from app.risk import engine as risk
from app.risk import persistence as risk_store
from app.risk.config import ENGINE_VERSION as RISK_VERSION
from app.tracing import anchor as anchor_mod
from app.tracing import persistence as trace_store
from app.tracing.engine import trace
from app.tracing.models import TraceParams, TraceResult, TransfersUnavailable

log = logging.getLogger("worker")

HEARTBEAT = Path("/tmp/tracefall-worker-heartbeat")  # noqa: S108
STALE_AFTER_SECONDS = 30
POLL_TIMEOUT_SECONDS = 5


def beat() -> None:
    HEARTBEAT.write_text(str(time.time()))


def is_alive() -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) < STALE_AFTER_SECONDS
    except (OSError, ValueError):
        return False


async def _retrieve(run: AnalysisRun, session: AsyncSession) -> AddressData:
    """RETRIEVAL stage — required. Without data there is nothing to analyse."""
    address = await session.get(Address, run.root_address_id)
    if address is None:
        raise RuntimeError(f"analysis run {run.id} references a missing address")
    chain = await session.get(Chain, address.chain_id)
    if chain is None:
        raise RuntimeError(f"address {address.id} references a missing chain")
    window = TimeWindow.last_days(int(run.params.get("time_window_days", 90)))

    return await service.retrieve_address(
        chain.code,
        address.address,
        window,
        session=session,
        case_id=run.case_id,
        analysis_run_id=run.id,
    )


def _fetcher(
    session: AsyncSession,
    run: AnalysisRun,
    chain: ChainCode,
    window: TimeWindow,
    already_retrieved: set[str],
) -> Callable[[str], Awaitable[list[NormalizedTransfer]]]:
    """The engine's data source: the canonical layer, filled on demand.

    An address the trace has not seen before is retrieved and normalized first. When that
    cannot be done the callback raises rather than returning an empty list, because an
    empty list means "this address sent nothing onward" — a finding we have not earned.
    """

    async def fetch(address: str) -> list[NormalizedTransfer]:
        if address not in already_retrieved:
            try:
                data = await service.retrieve_address(
                    chain,
                    address,
                    window,
                    session=session,
                    case_id=run.case_id,
                    analysis_run_id=run.id,
                )
            except FixtureMissing:
                raise TransfersUnavailable(
                    address, "no fixture is committed for this address"
                ) from None
            # Retrieval never raises on provider failure; it returns what it got and says
            # what it lost. Nothing retrieved plus a stated failure is not "no activity".
            if data.record_count == 0 and data.degradations:
                raise TransfersUnavailable(address, "; ".join(data.degradations))
            await normalize.normalize_address_data(session, data)
            already_retrieved.add(address)
        return (await intel.load_transfers(session, chain, [address]))[address]

    return fetch


async def _anchor(
    session: AsyncSession, run: AnalysisRun, chain: ChainCode, address: str
) -> tuple[anchor_mod.AnchorResult, list[NormalizedTransfer]]:
    """Find the victim's transfer among everything the suspect address received."""
    transfers = (await intel.load_transfers(session, chain, [address]))[address]
    reported = await session.scalar(
        select(CaseAddress).where(
            CaseAddress.case_id == run.case_id,
            CaseAddress.address_id == run.root_address_id,
        )
    )
    result = anchor_mod.resolve(
        transfers,
        address,
        reported.reported_amount if reported else None,
        reported.reported_at if reported else None,
        reported.reported_asset_symbol if reported else None,
    )
    return result, transfers


def _trace_subject(
    anchored: anchor_mod.AnchorResult, transfers: list[NormalizedTransfer], address: str
) -> tuple[int, str | None]:
    """What to trace: the victim's transfer, or everything the address received.

    Without an anchor the trace is far noisier, which is why the intake form asks — but an
    unanchored trace is still worth running, so this falls back to everything the address
    received in the asset it handles most.

    That asset is chosen **by transfer count, not by amount**: raw amounts at different
    precisions are not comparable, so picking the largest total would hand the trace to
    whichever token has the most decimals — reliably a dusted lookalike or a junk airdrop
    rather than the USDT the victim actually sent.
    """
    if anchored.transfer is not None:
        return anchored.transfer.amount_raw, anchored.transfer.asset_key

    asset_key = intel_features.dominant_asset([t for t in transfers if t.succeeded], address)
    if asset_key is None:
        return 0, None
    total = sum(
        t.amount_raw
        for t in transfers
        if t.to_address == address and t.succeeded and t.asset_key == asset_key
    )
    return total, asset_key


async def _trace(
    session: AsyncSession, run: AnalysisRun, chain: ChainCode, address: str, window: TimeWindow
) -> tuple[TraceResult | None, dict[str, object]]:
    """TRACING stage — required. Without it there is no fund flow to analyse."""
    anchored, transfers = await _anchor(session, run, chain, address)
    original_amount, asset_key = _trace_subject(anchored, transfers, address)
    summary: dict[str, object] = {
        "anchored": anchored.anchored,
        "anchor_reason": anchored.reason,
        "anchor_candidates": len(anchored.candidates),
        "asset_key": asset_key,
        "original_amount_raw": str(original_amount),
    }
    if original_amount <= 0 or asset_key is None:
        summary["skipped"] = "the root address received nothing that could be traced"
        return None, summary

    params = TraceParams(
        asset_key=asset_key,
        max_depth=int(run.params.get("max_depth", 3)),
        taint_threshold=Fraction(str(run.params.get("taint_threshold", 0.01))),
        stop_at_services=bool(run.params.get("stop_at_services", True)),
        window=window,
    )
    result = await trace(
        address,
        original_amount,
        _fetcher(session, run, chain, window, {address}),
        params,
        is_service_boundary=attribution.ServiceBoundaryChecker(session, chain),
        anchor_tx_hash=anchored.transfer.tx_hash if anchored.transfer else None,
        anchor_time=anchored.transfer.block_time if anchored.transfer else None,
    )
    await trace_store.save(session, run, result, chain)
    summary.update(
        nodes=len(result.nodes),
        edges=len(result.edges),
        unavailable=result.unavailable,
        pruned_share=float(result.pruned_share),
    )
    return result, summary


async def _graph_and_patterns(
    session: AsyncSession, run: AnalysisRun, chain: ChainCode, result: TraceResult
) -> tuple[dict[str, object], dict[str, object]]:
    """GRAPH and PATTERNS stages — both degradable.

    The graph is not persisted: it is derived from the trace, and rebuilding it on read
    is cheaper than keeping a second copy in step with the first. It is built here because
    the detectors run over it.
    """
    graph = builder.build(result)
    graph_summary: dict[str, object] = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
    }

    transfers = await intel.load_transfers(session, chain, list(graph.nodes))
    findings = run_all(Subject(graph=graph, transfers=transfers))
    written = await pattern_store.save(session, run.id, chain, findings)
    return graph_summary, {
        "findings": written,
        "unavailable_detectors": findings.unavailable,
    }


async def _score_risk(
    session: AsyncSession,
    run: AnalysisRun,
    chain: ChainCode,
    result: TraceResult,
    complete: bool,
) -> dict[str, object]:
    """RISK stage — degradable. Runs last because it reads every earlier stage's output."""
    graph = builder.build(result)
    attributions = await attribution.load(session, run.id)
    features = await intel.build_profiles(
        session, chain, list(result.nodes), result.params.asset_key
    )
    findings = await pattern_store.load(session, run.id, chain)
    assessments = risk.score_all(
        risk.Inputs(
            trace=result,
            graph=graph,
            features=features,
            attributions=attributions,
            findings=findings,
            cross_case=await _cross_case_matches(session, run, chain, list(result.nodes)),
            data_complete=complete,
            asset_symbol=result.edges[0].asset_symbol if result.edges else None,
        )
    )
    written = await risk_store.save(session, run.id, run.case_id, chain, assessments)
    root = assessments.get(result.root)
    return {
        "scored": written,
        "config_version": next(iter(assessments.values())).config_version if assessments else None,
        "root_score": root.score if root else None,
        "root_band": str(root.band) if root else None,
        "bands": Counter(str(a.band) for a in assessments.values()),
    }


async def _cross_case_matches(
    session: AsyncSession, run: AnalysisRun, chain: ChainCode, addresses: list[str]
) -> dict[str, bool]:
    """Which of these addresses already appear in another case (FR-103)."""
    seen = {
        address
        for (address,) in await session.execute(
            select(Address.address)
            .join(CaseAddress, CaseAddress.address_id == Address.id)
            .join(Chain, Chain.id == Address.chain_id)
            .where(
                Chain.code == chain,
                Address.address.in_(set(addresses)),
                CaseAddress.case_id != run.case_id,
            )
        )
    }
    return {address: address in seen for address in addresses}


async def _attribute(
    session: AsyncSession, run: AnalysisRun, chain: ChainCode, result: TraceResult
) -> dict[str, object]:
    """ATTRIBUTION stage — degradable, and the one that answers PS26183."""
    results = await attribution.attribute(
        session, chain, list(result.nodes), result.params.asset_key
    )
    written = await attribution.persist(session, run.id, chain, results)
    tiers: dict[str, int] = {}
    for outcome in results.values():
        tiers[str(outcome.tier)] = tiers.get(str(outcome.tier), 0) + 1
    return {"attributed": written, "tiers": tiers}


async def _run_pipeline(run_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        run = await session.get(AnalysisRun, run_id)
        if run is None or run.status != AnalysisStatus.QUEUED:
            return
        run.status = AnalysisStatus.RUNNING
        run.started_at = datetime.now(UTC)
        run.heartbeat_at = datetime.now(UTC)
        run.stage = AnalysisStage.RETRIEVAL
        await session.commit()

    if await queue.is_cancelled(run_id):
        return

    async with SessionFactory() as session:
        run = await session.get(AnalysisRun, run_id)
        if run is None:
            return
        degradations: list[dict[str, object]] = []
        try:
            data = await _retrieve(run, session)
        except FixtureMissing as exc:
            # An operator error, not a provider failure: fail loudly rather than
            # reporting an address with no activity.
            run.status = AnalysisStatus.FAILED
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await session.commit()
            log.error("analysis run %s has no fixture: %s", run_id, exc)
            return

        summary: dict[str, object] = {
            "records": data.record_count,
            "complete": data.complete,
            "truncation": data.truncation_reasons,
            "is_fixture": data.is_fixture,
            "degradations": data.degradations,
        }
        run.stage = AnalysisStage.NORMALIZATION
        run.progress_pct = 20
        await session.commit()

        # NORMALIZATION is required, not degradable: unnormalized data is not analysable,
        # so a failure here fails the run rather than producing a smaller answer.
        normalized = await normalize.normalize_address_data(session, data)

        engine_versions: dict[str, object] = {
            "ingestion": "1.0.0",
            "normalize": "1.0.0",
            "retrieval_summary": summary,
            "normalization_summary": normalized.as_dict(),
        }
        if summary["degradations"] or not summary["complete"]:
            degradations.append({"stage": AnalysisStage.RETRIEVAL, "detail": summary})

        address = await session.get(Address, run.root_address_id)
        chain_row = await session.get(Chain, address.chain_id) if address else None
        assert address is not None and chain_row is not None
        window = TimeWindow.last_days(int(run.params.get("time_window_days", 90)))

        run.stage = AnalysisStage.TRACING
        run.progress_pct = 40
        await session.commit()
        traced, trace_summary = await _trace(session, run, chain_row.code, address.address, window)
        engine_versions["tracing"] = "1.0.0"
        engine_versions["trace_summary"] = trace_summary
        if trace_summary.get("unavailable") or trace_summary.get("skipped"):
            degradations.append({"stage": AnalysisStage.TRACING, "detail": trace_summary})

        # Everything past here is degradable. An investigator holding a trace but no
        # pattern findings still has the answer they came for.
        if traced is not None:
            run.stage = AnalysisStage.GRAPH
            run.progress_pct = 60
            await session.commit()
            try:
                graph_summary, pattern_summary = await _graph_and_patterns(
                    session, run, chain_row.code, traced
                )
            except Exception as exc:  # noqa: BLE001 — one stage must not cost the rest
                log.exception("graph and pattern stages failed for run %s", run_id)
                await session.rollback()
                degradations.append({"stage": AnalysisStage.GRAPH, "detail": {"error": repr(exc)}})
            else:
                engine_versions["graph"] = "1.0.0"
                engine_versions["graph_summary"] = graph_summary
                engine_versions["patterns"] = DETECTOR_VERSION
                engine_versions["pattern_summary"] = pattern_summary
                if pattern_summary["unavailable_detectors"]:
                    degradations.append(
                        {"stage": AnalysisStage.PATTERNS, "detail": pattern_summary}
                    )

            run.stage = AnalysisStage.ATTRIBUTION
            run.progress_pct = 85
            await session.commit()
            try:
                attribution_summary = await _attribute(session, run, chain_row.code, traced)
            except Exception as exc:  # noqa: BLE001
                log.exception("attribution stage failed for run %s", run_id)
                await session.rollback()
                degradations.append(
                    {"stage": AnalysisStage.ATTRIBUTION, "detail": {"error": repr(exc)}}
                )
            else:
                engine_versions["attribution"] = ATTRIBUTION_VERSION
                engine_versions["attribution_summary"] = attribution_summary

            run.stage = AnalysisStage.RISK
            run.progress_pct = 95
            await session.commit()
            try:
                risk_summary = await _score_risk(
                    session, run, chain_row.code, traced, bool(summary["complete"])
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("risk stage failed for run %s", run_id)
                await session.rollback()
                degradations.append({"stage": AnalysisStage.RISK, "detail": {"error": repr(exc)}})
            else:
                engine_versions["risk"] = RISK_VERSION
                engine_versions["risk_summary"] = risk_summary

        run.progress_pct = 100
        run.stage = None
        run.completed_at = datetime.now(UTC)
        run.engine_versions = engine_versions
        run.status = AnalysisStatus.PARTIAL if degradations else AnalysisStatus.COMPLETED
        run.degradations = degradations
        await session.commit()
    log.info("analysis run %s finished: %s", run_id, engine_versions)


async def _reclaim_stale_runs() -> None:
    """A worker that died mid-job leaves a RUNNING row; mark it failed on startup."""
    async with SessionFactory() as session:
        stale = await session.scalars(
            select(AnalysisRun).where(AnalysisRun.status == AnalysisStatus.RUNNING)
        )
        for run in stale.all():
            run.status = AnalysisStatus.FAILED
            run.error = "Worker restarted while this run was in progress"
            run.completed_at = datetime.now(UTC)
        await session.commit()


async def main() -> None:
    configure_logging()
    beat()
    await _reclaim_stale_runs()
    log.info("worker ready")
    while True:
        beat()
        raw = await queue.dequeue(timeout=POLL_TIMEOUT_SECONDS)
        if raw is None:
            continue
        try:
            await _run_pipeline(uuid.UUID(raw))
        except Exception:
            log.exception("analysis run %s failed", raw)
            with contextlib.suppress(Exception):
                async with SessionFactory() as session:
                    run = await session.get(AnalysisRun, uuid.UUID(raw))
                    if run is not None:
                        run.status = AnalysisStatus.FAILED
                        run.error = "Pipeline raised an unexpected error"
                        run.completed_at = datetime.now(UTC)
                        await session.commit()


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if is_alive() else 1)
    asyncio.run(main())
