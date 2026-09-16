import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import CurrentUser, SessionDep, get_accessible_case, require_role
from app.core.exceptions import Conflict, NotFound
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address, Chain
from app.db.models.case import CaseAddress, CaseTimelineEvent
from app.db.models.enums import AnalysisStatus, UserRole
from app.db.models.user import User
from app.orchestrator import queue
from app.schemas.analysis import AnalysisAccepted, AnalysisOut, AnalysisStart

router = APIRouter(tags=["analyses"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]
ACTIVE = (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)


@router.post("/cases/{case_id}/analyses", response_model=AnalysisAccepted, status_code=202)
async def start_analysis(
    case_id: uuid.UUID, payload: AnalysisStart, user: Investigator, session: SessionDep
) -> AnalysisAccepted:
    await get_accessible_case(case_id, user, session)

    case_address = await session.scalar(
        select(CaseAddress).where(
            CaseAddress.id == payload.address_id, CaseAddress.case_id == case_id
        )
    )
    if case_address is None:
        raise NotFound("Address not found on this case")

    active = await session.scalar(
        select(AnalysisRun.id).where(
            AnalysisRun.case_id == case_id,
            AnalysisRun.root_address_id == case_address.address_id,
            AnalysisRun.status.in_(ACTIVE),
        )
    )
    if active is not None:
        raise Conflict()

    run = AnalysisRun(
        case_id=case_id,
        root_address_id=case_address.address_id,
        params=payload.model_dump(mode="json"),
        status=AnalysisStatus.QUEUED,
        triggered_by=user.id,
    )
    session.add(run)
    await session.flush()
    session.add(
        CaseTimelineEvent(
            case_id=case_id,
            actor_id=user.id,
            event_type="analysis.started",
            payload={"analysis_run_id": str(run.id)},
        )
    )
    await session.commit()
    await queue.enqueue(run.id)

    return AnalysisAccepted(
        analysis_run_id=run.id,
        status=AnalysisStatus.QUEUED,
        poll_url=f"/api/v1/analyses/{run.id}",
        estimated_seconds=75,
    )


async def _accessible_run(run_id: uuid.UUID, user: User, session: SessionDep) -> AnalysisRun:
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFound("Analysis run not found")
    await get_accessible_case(run.case_id, user, session)
    return run


# Results exist once a stage has persisted something; RUNNING qualifies, QUEUED does not.
_HAS_RESULTS = (AnalysisStatus.RUNNING, AnalysisStatus.PARTIAL, AnalysisStatus.COMPLETED)


_DERIVED_FIELDS = {"root_address", "partial_results_available"}


async def _to_out(run: AnalysisRun, session: SessionDep) -> AnalysisOut:
    """One conversion, so status semantics cannot drift between endpoints."""
    address = await session.get(Address, run.root_address_id)
    chain = await session.get(Chain, address.chain_id) if address else None
    return AnalysisOut(
        **{
            field: getattr(run, field)
            for field in AnalysisOut.model_fields
            if field not in _DERIVED_FIELDS and hasattr(run, field)
        },
        root_address=address.address if address else None,
        root_chain=chain.code if chain else None,
        partial_results_available=run.status in _HAS_RESULTS,
    )


@router.get("/analyses/{run_id}", response_model=AnalysisOut)
async def get_analysis(run_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> AnalysisOut:
    run = await _accessible_run(run_id, user, session)
    return await _to_out(run, session)


@router.post("/analyses/{run_id}/cancel", response_model=AnalysisOut, status_code=202)
async def cancel_analysis(
    run_id: uuid.UUID, user: Investigator, session: SessionDep
) -> AnalysisOut:
    run = await _accessible_run(run_id, user, session)
    if run.status in ACTIVE:
        await queue.request_cancel(run.id)
        run.status = AnalysisStatus.CANCELLED
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
    return await _to_out(run, session)


@router.get("/cases/{case_id}/analyses", response_model=list[AnalysisOut])
async def list_analyses(
    case_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[AnalysisOut]:
    await get_accessible_case(case_id, user, session)
    rows = await session.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    return [await _to_out(r, session) for r in rows.all()]
