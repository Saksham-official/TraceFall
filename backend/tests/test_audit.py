"""Audit logging (NFR-09, ADR-013)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog
from tests.conftest import auth, login, make_user


async def _rows(session: AsyncSession) -> list[AuditLog]:
    return list((await session.scalars(select(AuditLog).order_by(AuditLog.id))).all())


async def test_mutations_are_audited_with_the_actor(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session, "audited@example.gov")
    token = await login(client, "audited@example.gov")
    await client.post("/api/v1/cases", json={"title": "Audited case"}, headers=auth(token))

    entries = await _rows(session)
    created = [e for e in entries if e.resource_type == "cases" and e.action.startswith("POST")]
    assert created, "case creation was not audited"
    assert created[-1].actor_id == user.id
    assert created[-1].payload_sha256 is not None


async def test_case_reads_are_audited(client: AsyncClient, session: AsyncSession) -> None:
    """Who looked at which case is itself security-relevant."""
    await make_user(session, "reader@example.gov")
    token = await login(client, "reader@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Watched"}, headers=auth(token))
    ).json()["id"]
    await client.get(f"/api/v1/cases/{case_id}", headers=auth(token))

    reads = [e for e in await _rows(session) if e.action.startswith("GET")]
    assert reads, "case read was not audited"
    assert str(reads[-1].case_id) == case_id


async def test_health_checks_are_not_audited(client: AsyncClient, session: AsyncSession) -> None:
    await client.get("/api/v1/health")
    assert await _rows(session) == []


async def test_audit_entries_carry_the_request_correlation_id(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "corr@example.gov")
    token = await login(client, "corr@example.gov")
    response = await client.post("/api/v1/cases", json={"title": "Correlated"}, headers=auth(token))
    request_id = response.headers["X-Request-ID"]
    assert request_id
    assert any(e.request_id == request_id for e in await _rows(session))


async def test_failed_authorisation_is_still_audited(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.db.models.enums import UserRole

    await make_user(session, "denied@example.gov", UserRole.VIEWER)
    token = await login(client, "denied@example.gov")
    await client.post("/api/v1/cases", json={"title": "Refused"}, headers=auth(token))
    assert any("403" in e.action for e in await _rows(session))
