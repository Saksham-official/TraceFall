"""Analysis queue worker.

Phase 2 runs a stub pipeline: it claims a queued run, marks it RUNNING, heartbeats, and
completes it. Phase 3 onward replaces _run_pipeline with the real stages.
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

from app.core.logging import configure_logging
from app.db.models.analysis import AnalysisRun
from app.db.models.enums import AnalysisStage, AnalysisStatus
from app.db.session import SessionFactory
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
        # Phase 3 onward replaces this with the real stage sequence.
        run.status = AnalysisStatus.COMPLETED
        run.stage = None
        run.progress_pct = 100
        run.completed_at = datetime.now(UTC)
        run.engine_versions = {"pipeline": "stub-phase2"}
        await session.commit()
    log.info("completed analysis run %s (stub pipeline)", run_id)


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
