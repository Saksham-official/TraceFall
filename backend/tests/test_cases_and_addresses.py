from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth, login, make_user

USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_ERC20 = "0xdAC17F958D2ee523a2206206994597C13D831ec7"


async def _token(client: AsyncClient, session: AsyncSession, email: str) -> str:
    await make_user(session, email)
    return await login(client, email)


async def test_case_creation_assigns_a_sequential_number(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "num@example.gov")
    first = await client.post(
        "/api/v1/cases",
        json={"title": "USDT investment fraud", "ncrp_reference": "NCRP2026030112345"},
        headers=auth(token),
    )
    second = await client.post("/api/v1/cases", json={"title": "Second"}, headers=auth(token))
    assert first.status_code == 201
    assert first.json()["case_number"].startswith("TF-")
    assert first.json()["case_number"] != second.json()["case_number"]
    assert first.json()["status"] == "OPEN"


async def test_case_stores_no_victim_pii_fields(client: AsyncClient, session: AsyncSession) -> None:
    """ADR-011: reference numbers only. There is nowhere to put a victim's name."""
    token = await _token(client, session, "pii@example.gov")
    body = (await client.post("/api/v1/cases", json={"title": "Case"}, headers=auth(token))).json()
    forbidden = {"victim_name", "victim_phone", "victim_email", "victim_address", "bank_account"}
    assert forbidden.isdisjoint(body.keys())


async def test_case_timeline_records_creation_and_updates(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "timeline@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Tracked"}, headers=auth(token))
    ).json()["id"]
    await client.patch(f"/api/v1/cases/{case_id}", json={"status": "REVIEW"}, headers=auth(token))
    events = (await client.get(f"/api/v1/cases/{case_id}/timeline", headers=auth(token))).json()
    assert {e["event_type"] for e in events} == {"case.created", "case.updated"}


async def test_closing_a_case_sets_closed_at(client: AsyncClient, session: AsyncSession) -> None:
    token = await _token(client, session, "close@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Closing"}, headers=auth(token))
    ).json()["id"]
    updated = await client.patch(
        f"/api/v1/cases/{case_id}", json={"status": "CLOSED"}, headers=auth(token)
    )
    assert updated.json()["closed_at"] is not None


async def test_case_search_matches_the_ncrp_reference(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "search@example.gov")
    await client.post(
        "/api/v1/cases",
        json={"title": "Findable", "ncrp_reference": "NCRP2026030112345"},
        headers=auth(token),
    )
    await client.post("/api/v1/cases", json={"title": "Other"}, headers=auth(token))
    found = await client.get("/api/v1/cases?q=NCRP20260301", headers=auth(token))
    assert [c["title"] for c in found.json()["items"]] == ["Findable"]


async def test_adding_a_valid_address(client: AsyncClient, session: AsyncSession) -> None:
    token = await _token(client, session, "addr@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Trace"}, headers=auth(token))
    ).json()["id"]
    added = await client.post(
        f"/api/v1/cases/{case_id}/addresses",
        json={"address": USDT_TRC20, "reported_at": "2026-08-14T09:32:00Z"},
        headers=auth(token),
    )
    assert added.status_code == 201
    assert added.json()["chain"] == "TRON"
    assert added.json()["cross_case_matches"] == []


async def test_ethereum_address_is_stored_lowercase_and_displayed_checksummed(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "eth@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Eth"}, headers=auth(token))
    ).json()["id"]
    body = (
        await client.post(
            f"/api/v1/cases/{case_id}/addresses",
            json={"address": USDT_ERC20},
            headers=auth(token),
        )
    ).json()
    assert body["address"] == USDT_ERC20.lower()
    assert body["display_address"] == USDT_ERC20


async def test_invalid_address_is_rejected_before_any_network_call(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "bad@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Bad"}, headers=auth(token))
    ).json()["id"]
    response = await client.post(
        f"/api/v1/cases/{case_id}/addresses",
        json={"address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6X"},
        headers=auth(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ADDRESS"
    assert "Checksum" in response.json()["error"]["message"]


async def test_unsupported_chain_gets_a_named_hint(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _token(client, session, "btc@example.gov")
    case_id = (
        await client.post("/api/v1/cases", json={"title": "Btc"}, headers=auth(token))
    ).json()["id"]
    response = await client.post(
        f"/api/v1/cases/{case_id}/addresses",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"},
        headers=auth(token),
    )
    assert response.status_code == 422
    assert "Bitcoin" in response.json()["error"]["message"]


async def test_same_address_in_a_second_case_is_flagged_at_intake(
    client: AsyncClient, session: AsyncSession
) -> None:
    """An investigator must learn immediately that another case shares this address."""
    token = await _token(client, session, "cross@example.gov")
    first = (
        await client.post("/api/v1/cases", json={"title": "First"}, headers=auth(token))
    ).json()
    second = (
        await client.post("/api/v1/cases", json={"title": "Second"}, headers=auth(token))
    ).json()
    await client.post(
        f"/api/v1/cases/{first['id']}/addresses",
        json={"address": USDT_TRC20},
        headers=auth(token),
    )
    body = (
        await client.post(
            f"/api/v1/cases/{second['id']}/addresses",
            json={"address": USDT_TRC20},
            headers=auth(token),
        )
    ).json()
    assert [m["case_number"] for m in body["cross_case_matches"]] == [first["case_number"]]


async def test_address_is_stored_once_and_shared_across_cases(
    client: AsyncClient, session: AsyncSession
) -> None:
    from sqlalchemy import func, select

    from app.db.models.blockchain import Address

    token = await _token(client, session, "shared@example.gov")
    for title in ("Case one", "Case two"):
        case_id = (
            await client.post("/api/v1/cases", json={"title": title}, headers=auth(token))
        ).json()["id"]
        await client.post(
            f"/api/v1/cases/{case_id}/addresses",
            json={"address": USDT_TRC20},
            headers=auth(token),
        )
    count = await session.scalar(
        select(func.count()).select_from(Address).where(Address.address == USDT_TRC20)
    )
    assert count == 1
