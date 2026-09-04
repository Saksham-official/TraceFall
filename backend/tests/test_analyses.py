"""Job lifecycle: enqueue, claim, complete, report status."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.db.models.analysis import AnalysisRun
from app.db.models.enums import AnalysisStatus
from app.orchestrator import queue
from tests.conftest import auth, login, make_user

# The address the committed fixtures were captured for, so the pipeline has real data.
FIXTURED_ADDRESS = "TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9"
UNFIXTURED_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


async def _case_with_address(client: AsyncClient, session: AsyncSession, email: str) -> tuple:
    await make_user(session, email)
    token = await login(client, email)
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Analysis case"}, headers=auth(token))
    ).json()["id"]
    address = (
        await client.post(
            f"/api/v1/cases/{case_id}/addresses",
            json={"address": FIXTURED_ADDRESS},
            headers=auth(token),
        )
    ).json()
    return token, case_id, address["id"]


async def test_starting_an_analysis_enqueues_a_job(
    client: AsyncClient, session: AsyncSession
) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "job@example.gov")
    started = await client.post(
        f"/api/v1/cases/{case_id}/analyses",
        json={"address_id": address_id, "max_depth": 5},
        headers=auth(token),
    )
    assert started.status_code == 202
    body = started.json()
    assert body["status"] == "QUEUED"
    assert body["poll_url"].endswith(body["analysis_run_id"])
    assert await queue.depth() == 1


async def test_status_is_pollable(client: AsyncClient, session: AsyncSession) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "poll@example.gov")
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]
    status = await client.get(f"/api/v1/analyses/{run_id}", headers=auth(token))
    assert status.status_code == 200
    assert status.json()["status"] == "QUEUED"
    assert status.json()["progress_pct"] == 0


async def test_worker_claims_the_job_and_completes_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "worker@example.gov")
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]

    claimed = await queue.dequeue(timeout=2)
    assert claimed == run_id
    await worker._run_pipeline(uuid.UUID(run_id))

    status = (await client.get(f"/api/v1/analyses/{run_id}", headers=auth(token))).json()
    assert status["status"] == "COMPLETED"
    assert status["progress_pct"] == 100
    assert status["completed_at"] is not None


async def test_missing_fixture_fails_the_run_loudly(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Reporting "no activity" for an address we simply never captured would be a lie."""
    await make_user(session, "nofixture@example.gov")
    token = await login(client, "nofixture@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "No fixture"}, headers=auth(token))
    ).json()["id"]
    address_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/addresses",
            json={"address": UNFIXTURED_ADDRESS},
            headers=auth(token),
        )
    ).json()["id"]
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]

    await queue.dequeue(timeout=2)
    await worker._run_pipeline(uuid.UUID(run_id))

    status = (await client.get(f"/api/v1/analyses/{run_id}", headers=auth(token))).json()
    assert status["status"] == "FAILED"
    assert "capture_fixtures" in (status["error"] or "")


async def test_completed_run_records_what_was_retrieved(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.db.models.analysis import AnalysisRun

    token, case_id, address_id = await _case_with_address(client, session, "summary@example.gov")
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]
    await queue.dequeue(timeout=2)
    await worker._run_pipeline(uuid.UUID(run_id))

    run = await session.get(AnalysisRun, uuid.UUID(run_id))
    assert run is not None
    await session.refresh(run)
    summary = run.engine_versions["retrieval_summary"]
    assert summary["records"] > 0
    assert summary["is_fixture"] is True


async def test_duplicate_analysis_for_the_same_address_conflicts(
    client: AsyncClient, session: AsyncSession
) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "dup@example.gov")
    payload = {"address_id": address_id}
    first = await client.post(
        f"/api/v1/cases/{case_id}/analyses", json=payload, headers=auth(token)
    )
    second = await client.post(
        f"/api/v1/cases/{case_id}/analyses", json=payload, headers=auth(token)
    )
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ANALYSIS_IN_PROGRESS"


async def test_analysis_can_be_cancelled(client: AsyncClient, session: AsyncSession) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "cancel@example.gov")
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]

    cancelled = await client.post(f"/api/v1/analyses/{run_id}/cancel", headers=auth(token))
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"
    assert await queue.is_cancelled(run_id)

    # A cancelled run must not then be executed by a worker that already claimed it.
    await worker._run_pipeline(uuid.UUID(run_id))
    after = (await client.get(f"/api/v1/analyses/{run_id}", headers=auth(token))).json()
    assert after["status"] == "CANCELLED"


async def test_analysis_rejects_an_address_from_another_case(
    client: AsyncClient, session: AsyncSession
) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "mix@example.gov")
    other_case = (
        await client.post("/api/v1/cases", json={"title": "Other case"}, headers=auth(token))
    ).json()["id"]
    response = await client.post(
        f"/api/v1/cases/{other_case}/analyses",
        json={"address_id": address_id},
        headers=auth(token),
    )
    assert response.status_code == 404


async def test_worker_restart_fails_runs_left_in_progress(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A worker that dies mid-job must not leave a run RUNNING forever."""
    token, case_id, address_id = await _case_with_address(client, session, "stale@example.gov")
    run_id = (
        await client.post(
            f"/api/v1/cases/{case_id}/analyses",
            json={"address_id": address_id},
            headers=auth(token),
        )
    ).json()["analysis_run_id"]

    run = await session.get(AnalysisRun, uuid.UUID(run_id))
    assert run is not None
    run.status = AnalysisStatus.RUNNING
    await session.commit()

    await worker._reclaim_stale_runs()

    refreshed = await session.scalar(select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(run_id)))
    await session.refresh(refreshed)  # type: ignore[arg-type]
    assert refreshed is not None
    assert refreshed.status == AnalysisStatus.FAILED
    assert "Worker restarted" in (refreshed.error or "")


async def test_depth_beyond_the_maximum_is_rejected(
    client: AsyncClient, session: AsyncSession
) -> None:
    token, case_id, address_id = await _case_with_address(client, session, "depth@example.gov")
    response = await client.post(
        f"/api/v1/cases/{case_id}/analyses",
        json={"address_id": address_id, "max_depth": 99},
        headers=auth(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
