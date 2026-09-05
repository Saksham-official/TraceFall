"""Analysis queue worker.

Runs the analysis pipeline stage by stage. RETRIEVAL and NORMALIZATION are implemented;
the remaining stages land in later phases. Each stage declares whether it is required or
degradable: a degradable stage that fails records why and lets the run continue as
PARTIAL, because a partial answer with its limits stated is worth more than no answer.
"""

import asyncio
import contextlib
import logging
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.base import TimeWindow
from app.core.logging import configure_logging
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address, Chain
from app.db.models.enums import AnalysisStage, AnalysisStatus
from app.db.session import SessionFactory
from app.ingestion import service
from app.ingestion.fixtures import FixtureMissing
from app.ingestion.service import AddressData
from app.normalize import service as normalize
from app.orchestrator import queue

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
        run.progress_pct = 50
        await session.commit()

        # NORMALIZATION is required, not degradable: unnormalized data is not analysable,
        # so a failure here fails the run rather than producing a smaller answer.
        normalized = await normalize.normalize_address_data(session, data)

        run.progress_pct = 100
        run.stage = None
        run.completed_at = datetime.now(UTC)
        run.engine_versions = {
            "ingestion": "1.0.0",
            "normalize": "1.0.0",
            "retrieval_summary": summary,
            "normalization_summary": normalized.as_dict(),
        }
        if summary["degradations"] or not summary["complete"]:
            degradations.append({"stage": AnalysisStage.RETRIEVAL, "detail": summary})
            run.status = AnalysisStatus.PARTIAL
        else:
            run.status = AnalysisStatus.COMPLETED
        run.degradations = degradations
        await session.commit()
    log.info("analysis run %s finished: %s, %s", run_id, summary, normalized.as_dict())


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
