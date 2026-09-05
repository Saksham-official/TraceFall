"""Alerts: the findings that should interrupt an investigator rather than wait (FR-100..102).

The rows are written by the risk stage — sanctions contact, mixer contact, and a
`CRITICAL` score (`risk/persistence.py`). This module only reads them back, per case and
globally, and records an acknowledgement.

**Case isolation is applied to the query, not to the response.** The global list carries
the same visibility rule the case list uses, so an alert on a case a user cannot see never
enters the result set — rather than being filtered out of one that was already built.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Row, Select, or_, select

from app.core.deps import SessionDep, get_accessible_case, require_role
from app.core.exceptions import NotFound
from app.db.models.blockchain import Address
from app.db.models.case import Case, CaseAssignment
from app.db.models.enums import AlertType, Severity, UserRole
from app.db.models.finding import Alert
from app.db.models.user import User
from app.schemas.alert import AlertOut
from app.schemas.common import Page, decode_cursor, encode_cursor

router = APIRouter(tags=["alerts"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]

# Mirrors app.core.deps: these roles read every case, so they see every alert.
_GLOBAL_READERS = {UserRole.ADMIN, UserRole.ANALYST}


def _base() -> Select[tuple[Alert, str | None]]:
    """Alerts with the address they name — outer joined, because not every alert has one."""
    stmt: Select[tuple[Alert, str | None]] = select(Alert, Address.address)
    return stmt.outerjoin(Address, Address.id == Alert.address_id)


def _visible(
    stmt: Select[tuple[Alert, str | None]], user: User
) -> Select[tuple[Alert, str | None]]:
    if user.role in _GLOBAL_READERS:
        return stmt
    return (
        stmt.join(Case, Case.id == Alert.case_id)
        .outerjoin(CaseAssignment, CaseAssignment.case_id == Case.id)
        .where(or_(Case.owner_id == user.id, CaseAssignment.user_id == user.id))
    )


def _out(alert: Alert, address: str | None) -> AlertOut:
    return AlertOut(
        id=alert.id,
        case_id=alert.case_id,
        analysis_run_id=alert.analysis_run_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        address=address,
        trigger_reason=alert.trigger_reason,
        source_finding_type=alert.source_finding_type,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        created_at=alert.created_at,
    )


async def _page(
    stmt: Select[tuple[Alert, str | None]], session: SessionDep, limit: int, cursor: str | None
) -> Page[AlertOut]:
    if cursor and (raw := decode_cursor(cursor)):
        stmt = stmt.where(Alert.created_at < datetime.fromisoformat(raw))
    rows: list[Row[tuple[Alert, str | None]]] = list(
        (
            await session.execute(
                stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return Page[AlertOut](
        items=[_out(alert, address) for alert, address in rows],
        next_cursor=(
            encode_cursor(rows[-1][0].created_at.isoformat()) if has_more and rows else None
        ),
        has_more=has_more,
    )


@router.get("/alerts")
async def list_alerts(
    user: Investigator,
    session: SessionDep,
    alert_type: AlertType | None = None,
    severity: Severity | None = None,
    unacknowledged: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
) -> Page[AlertOut]:
    """Every alert the user may see, newest first (FR-101).

    `unacknowledged` defaults to true: the list exists to show what still needs a look.
    """
    stmt = _visible(_base(), user)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if unacknowledged:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))
    return await _page(stmt, session, limit, cursor)


@router.get("/cases/{case_id}/alerts")
async def list_case_alerts(
    case_id: uuid.UUID,
    user: Investigator,
    session: SessionDep,
    unacknowledged: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> Page[AlertOut]:
    """One case's alerts. 404 — never 403 — for a case the user cannot reach."""
    await get_accessible_case(case_id, user, session)
    stmt = _base().where(Alert.case_id == case_id)
    if unacknowledged:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))
    return await _page(stmt, session, limit, cursor)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id: int, user: Investigator, session: SessionDep) -> AlertOut:
    """Record who saw this and when (FR-102).

    Acknowledging twice keeps the first acknowledgement: the question the record answers
    is when someone first took responsibility for the alert, and a later click must not
    overwrite that.
    """
    row = (await session.execute(_base().where(Alert.id == alert_id))).first()
    if row is None:
        raise NotFound("Alert not found")
    alert, address = row
    await get_accessible_case(alert.case_id, user, session)

    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by = user.id
        await session.commit()
    return _out(alert, address)
