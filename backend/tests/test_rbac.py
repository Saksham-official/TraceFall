from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import UserRole
from tests.conftest import auth, login, make_user


async def test_viewer_cannot_create_a_case(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "viewer@example.gov", UserRole.VIEWER)
    token = await login(client, "viewer@example.gov")
    response = await client.post("/api/v1/cases", json={"title": "Attempt"}, headers=auth(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_investigator_cannot_delete_a_case(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "inv@example.gov", UserRole.INVESTIGATOR)
    token = await login(client, "inv@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Mine"}, headers=auth(token))
    ).json()["id"]
    assert (await client.delete(f"/api/v1/cases/{case_id}", headers=auth(token))).status_code == 403


async def test_admin_can_delete_a_case(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "root@example.gov", UserRole.ADMIN)
    token = await login(client, "root@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Disposable"}, headers=auth(token))
    ).json()["id"]
    assert (await client.delete(f"/api/v1/cases/{case_id}", headers=auth(token))).status_code == 204
