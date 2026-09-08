import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select

from app.core.deps import (
    CurrentUser,
    SessionDep,
    get_accessible_case,
    require_role,
    visible_cases,
)
from app.db import correlation
from app.db.models.case import Case, CaseNote, CaseTimelineEvent
from app.db.models.enums import CaseStatus, Priority, UserRole
from app.db.models.user import User
from app.schemas.case import (
    CaseCreate,
    CaseOut,
    CaseUpdate,
    CorrelationOut,
    LinkedCaseOut,
    NoteCreate,
    NoteOut,
    SharedAddressOut,
    TimelineEventOut,
)
from app.schemas.common import Page, decode_cursor, encode_cursor

router = APIRouter(prefix="/cases", tags=["cases"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]


async def _record(
    session: SessionDep, case_id: uuid.UUID, actor_id: int, event: str, **payload: object
) -> None:
    session.add(
        CaseTimelineEvent(case_id=case_id, actor_id=actor_id, event_type=event, payload=payload)
    )


@router.post("", response_model=CaseOut, status_code=201)
async def create_case(payload: CaseCreate, user: Investigator, session: SessionDep) -> Case:
    number = await session.scalar(select(func.nextval("case_number_seq")))
    case = Case(
        case_number=f"TF-{datetime.now(UTC).year}-{number:04d}",
        owner_id=user.id,
        **payload.model_dump(),
    )
    session.add(case)
    await session.flush()
    await _record(session, case.id, user.id, "case.created", case_number=case.case_number)
    await session.commit()
    await session.refresh(case)
    return case


@router.get("", response_model=Page[CaseOut])
async def list_cases(
    user: CurrentUser,
    session: SessionDep,
    status: CaseStatus | None = None,
    priority: Priority | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
) -> Page[CaseOut]:
    stmt = visible_cases(select(Case), user)
    if status:
        stmt = stmt.where(Case.status == status)
    if priority:
        stmt = stmt.where(Case.priority == priority)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Case.case_number.ilike(pattern),
                Case.ncrp_reference.ilike(pattern),
                Case.fir_reference.ilike(pattern),
                Case.title.ilike(pattern),
            )
        )
    if cursor and (raw := decode_cursor(cursor)):
        stmt = stmt.where(Case.created_at < datetime.fromisoformat(raw))

    rows = list(
        (await session.scalars(stmt.order_by(Case.created_at.desc()).limit(limit + 1))).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return Page[CaseOut](
        items=[CaseOut.model_validate(r) for r in rows],
        next_cursor=encode_cursor(rows[-1].created_at.isoformat()) if has_more and rows else None,
        has_more=has_more,
    )


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(case_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Case:
    return await get_accessible_case(case_id, user, session)


@router.patch("/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: uuid.UUID, payload: CaseUpdate, user: Investigator, session: SessionDep
) -> Case:
    case = await get_accessible_case(case_id, user, session)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(case, field, value)
    if changes.get("status") == CaseStatus.CLOSED:
        case.closed_at = datetime.now(UTC)
    await _record(
        session, case.id, user.id, "case.updated", **{k: str(v) for k, v in changes.items()}
    )
    await session.commit()
    await session.refresh(case)
    return case


@router.post("/{case_id}/notes", response_model=NoteOut, status_code=201)
async def add_note(
    case_id: uuid.UUID, payload: NoteCreate, user: Investigator, session: SessionDep
) -> CaseNote:
    await get_accessible_case(case_id, user, session)
    note = CaseNote(case_id=case_id, author_id=user.id, **payload.model_dump())
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.get("/{case_id}/timeline", response_model=list[TimelineEventOut])
async def timeline(
    case_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[CaseTimelineEvent]:
    await get_accessible_case(case_id, user, session)
    rows = await session.scalars(
        select(CaseTimelineEvent)
        .where(CaseTimelineEvent.case_id == case_id)
        .order_by(CaseTimelineEvent.created_at.desc())
    )
    return list(rows.all())


@router.delete("/{case_id}", status_code=204)
async def delete_case(
    case_id: uuid.UUID,
    session: SessionDep,
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> Response:
    case = await get_accessible_case(case_id, user, session)
    await session.delete(case)
    await session.commit()
    return Response(status_code=204)


@router.get("/{case_id}/correlations", response_model=CorrelationOut)
async def get_correlations(
    case_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> CorrelationOut:
    """Addresses this case shares with other cases the caller can already open.

    The same fraud rarely produces one report. Ten victims paying into ten different
    suspect wallets that all sweep into one deposit address is one investigation, and one
    freeze request, rather than ten of each.
    """
    await get_accessible_case(case_id, user, session)
    shared = await correlation.shared_addresses(
        session, case_id, visible_cases(select(Case.id), user)
    )
    return CorrelationOut(
        shared_addresses=[
            SharedAddressOut(
                address=s.address,
                chain=s.chain,
                case_count=s.case_count,
                combined_reported_loss_inr=s.combined_reported_loss_inr,
                cases=[LinkedCaseOut(**vars(c)) for c in s.cases],
            )
            for s in shared
        ]
    )
