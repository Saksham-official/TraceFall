"""Case isolation (NFR-08).

The most important security suite in the system. A user must never reach another
investigator's case, and must receive 404 rather than 403 — a 403 confirms the case
exists, leaking that an investigation into a given address is underway (ADR-013).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import UserRole
from tests.conftest import auth, login, make_user

USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


async def _case_owned_by_a(client: AsyncClient, session: AsyncSession) -> tuple[str, str, str]:
    """Returns (case_id, token_a, token_b) where B is an unrelated investigator."""
    await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    await make_user(session, "bob@example.gov", UserRole.INVESTIGATOR)
    token_a = await login(client, "alice@example.gov")
    token_b = await login(client, "bob@example.gov")
    created = await client.post(
        "/api/v1/cases", json={"title": "Alice's investigation"}, headers=auth(token_a)
    )
    assert created.status_code == 201
    return created.json()["id"], token_a, token_b


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("get", "", None),
        ("patch", "", {"title": "hijacked title"}),
        ("get", "/timeline", None),
        ("post", "/notes", {"body": "inserted by another user"}),
        ("get", "/addresses", None),
        ("post", "/addresses", {"address": USDT_TRC20}),
        ("get", "/analyses", None),
        ("post", "/analyses", {"address_id": 1}),
    ],
)
async def test_other_investigator_gets_404_on_every_case_endpoint(
    client: AsyncClient, session: AsyncSession, method: str, suffix: str, body: dict | None
) -> None:
    case_id, _, token_b = await _case_owned_by_a(client, session)
    call = getattr(client, method)
    kwargs = {"headers": auth(token_b)}
    if body is not None:
        kwargs["json"] = body

    response = await call(f"/api/v1/cases/{case_id}{suffix}", **kwargs)

    # 403 would confirm the case exists. 404 is the only acceptable answer.
    assert response.status_code == 404, "403 leaks the existence of another user's case"


async def test_owner_can_reach_their_own_case(client: AsyncClient, session: AsyncSession) -> None:
    case_id, token_a, _ = await _case_owned_by_a(client, session)
    response = await client.get(f"/api/v1/cases/{case_id}", headers=auth(token_a))
    assert response.status_code == 200


async def test_case_list_excludes_other_users_cases(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, _, token_b = await _case_owned_by_a(client, session)
    listing = await client.get("/api/v1/cases", headers=auth(token_b))
    assert listing.status_code == 200
    assert listing.json()["items"] == []


async def test_analyst_may_read_across_cases(client: AsyncClient, session: AsyncSession) -> None:
    """Central analysts look across cases by design; investigators do not."""
    case_id, _, _ = await _case_owned_by_a(client, session)
    await make_user(session, "analyst@example.gov", UserRole.ANALYST)
    token = await login(client, "analyst@example.gov")
    assert (await client.get(f"/api/v1/cases/{case_id}", headers=auth(token))).status_code == 200


async def test_missing_and_forbidden_cases_are_indistinguishable(
    client: AsyncClient, session: AsyncSession
) -> None:
    case_id, _, token_b = await _case_owned_by_a(client, session)
    forbidden = await client.get(f"/api/v1/cases/{case_id}", headers=auth(token_b))
    absent = await client.get(f"/api/v1/cases/{uuid.uuid4()}", headers=auth(token_b))
    assert forbidden.status_code == absent.status_code == 404
    assert forbidden.json()["error"]["code"] == absent.json()["error"]["code"]


async def test_role_gated_delete_does_not_leak_case_existence(
    client: AsyncClient, session: AsyncSession
) -> None:
    """DELETE is admin-only, so a non-admin is refused before the case is ever looked up.

    That is not a leak, but only if the answer is identical for a case that exists and
    one that does not — which is what this asserts.
    """
    case_id, _, token_b = await _case_owned_by_a(client, session)
    existing = await client.delete(f"/api/v1/cases/{case_id}", headers=auth(token_b))
    absent = await client.delete(f"/api/v1/cases/{uuid.uuid4()}", headers=auth(token_b))
    assert existing.status_code == absent.status_code == 403
    assert existing.json()["error"]["code"] == absent.json()["error"]["code"]


async def test_admin_still_cannot_reach_a_case_that_does_not_exist(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, "admin2@example.gov", UserRole.ADMIN)
    token = await login(client, "admin2@example.gov")
    assert (
        await client.delete(f"/api/v1/cases/{uuid.uuid4()}", headers=auth(token))
    ).status_code == 404


async def test_unauthenticated_access_is_rejected(
    client: AsyncClient, session: AsyncSession
) -> None:
    case_id, _, _ = await _case_owned_by_a(client, session)
    assert (await client.get(f"/api/v1/cases/{case_id}")).status_code == 401
