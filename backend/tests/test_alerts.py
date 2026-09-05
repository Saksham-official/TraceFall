"""Alerts (FR-100, FR-101, FR-102).

An alert is the system interrupting an investigator. That earns two obligations, and both
are under test here: it must actually fire when the trace touches something that warrants
it — a sanctions match is a dataset fact, not a score to be triaged — and it must never
carry a case across the isolation boundary, because the existence of an alert reveals that
an investigation into a given address is underway.

The acknowledgement is a record of who first took responsibility. A second click must not
overwrite the first, or the record answers a different question than the one asked of it.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.chains.tron import adapter as tron
from app.db.models.blockchain import Address, Chain
from app.db.models.entity import Attribution
from app.db.models.enums import (
    AlertType,
    AttributionTier,
    ChainCode,
    Severity,
    UserRole,
)
from app.db.models.finding import Alert
from app.labels import loader
from app.normalize import service as normalize
from tests.conftest import auth, login, make_user
from tests.test_labels import dataset
from tests.test_normalize import FIXTURED_TRON_ADDRESS
from tests.test_pipeline import queued_run
from tests.tracing_fixtures import tx

NEXT_HOP = tron.from_hex("41" + f"{909:040x}")


def sanctioned_label(address: str) -> dict[str, str]:
    return {
        "chain": "TRON",
        "address": address,
        "entity": "OFAC SDN designated party",
        "entity_type": "SANCTIONED",
        "label_text": "OFAC SDN sanctioned address",
        "label_type": "SANCTIONED",
    }


async def run_reaching_a_sanctioned_address(session: AsyncSession) -> tuple[uuid.UUID, str]:
    """A completed run whose trace lands on a sanctioned address. Returns (run_id, email)."""
    await loader.ingest(session, dataset([sanctioned_label(NEXT_HOP)], name="Sanctions test"))

    senders = [tron.from_hex("41" + f"{910 + i:040x}") for i in range(3)]
    seeded = [
        tx(sender, FIXTURED_TRON_ADDRESS, 1_000_000, i * 10) for i, sender in enumerate(senders)
    ]
    seeded += [tx(FIXTURED_TRON_ADDRESS, NEXT_HOP, 1_000_000, 30 + i * 10) for i in range(3)]
    await normalize.persist(session, ChainCode.TRON, seeded)

    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)

    from app.db.models.analysis import AnalysisRun
    from app.db.models.user import User

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    owner = await session.get(User, run.triggered_by)
    assert owner is not None
    return run_id, owner.email


# --- The pipeline raises them (FR-100) ------------------------------------------------


async def test_a_trace_reaching_a_sanctioned_address_raises_an_alert(
    session: AsyncSession,
) -> None:
    """A sanctions match alerts on the match, not on the score it happens to have."""
    run_id, _ = await run_reaching_a_sanctioned_address(session)

    alerts = list(
        (await session.scalars(select(Alert).where(Alert.analysis_run_id == run_id))).all()
    )

    sanctioned = [a for a in alerts if a.alert_type is AlertType.SANCTIONED_CONTACT]
    assert sanctioned, "the sanctioned hop must interrupt the investigator"
    assert sanctioned[0].severity is Severity.HIGH
    assert NEXT_HOP in sanctioned[0].trigger_reason
    assert sanctioned[0].acknowledged_at is None


async def test_a_probable_sanctions_link_does_not_alert_as_a_fact(
    session: AsyncSession,
) -> None:
    """The root funnels into the sanctioned address, so it inherits the entity type.

    That inference is correct and it is reported — as `PROBABLE`, with its evidence. What
    it must not do is raise an alert reading "this address is on a sanctions list", which
    is an inference stated as a fact.
    """
    run_id, _ = await run_reaching_a_sanctioned_address(session)

    alerted = {
        address
        for (address,) in await session.execute(
            select(Address.address)
            .join(Alert, Alert.address_id == Address.id)
            .where(
                Alert.analysis_run_id == run_id,
                Alert.alert_type == AlertType.SANCTIONED_CONTACT,
            )
        )
    }
    tiers = {
        address: tier
        for address, tier in await session.execute(
            select(Address.address, Attribution.tier)
            .join(Attribution, Attribution.address_id == Address.id)
            .where(Attribution.analysis_run_id == run_id)
        )
    }

    assert tiers[FIXTURED_TRON_ADDRESS] is AttributionTier.PROBABLE
    assert FIXTURED_TRON_ADDRESS not in alerted
    assert alerted == {NEXT_HOP}


async def test_a_clean_trace_raises_nothing(session: AsyncSession) -> None:
    """An alert that fires on everything is an alert nobody reads."""
    senders = [tron.from_hex("41" + f"{920 + i:040x}") for i in range(2)]
    await normalize.persist(
        session,
        ChainCode.TRON,
        [tx(s, FIXTURED_TRON_ADDRESS, 1_000, i * 10) for i, s in enumerate(senders)],
    )
    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)

    assert (await session.scalars(select(Alert).where(Alert.analysis_run_id == run_id))).all() == []


# --- They are readable (FR-101) -------------------------------------------------------


async def test_the_global_list_returns_the_alert_with_its_address_and_reason(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email = await run_reaching_a_sanctioned_address(session)

    response = await client.get("/api/v1/alerts", headers=auth(await login(client, email)))

    assert response.status_code == 200
    items = response.json()["items"]
    alert = next(a for a in items if a["alert_type"] == "SANCTIONED_CONTACT")
    assert alert["address"] == NEXT_HOP
    assert alert["severity"] == "HIGH"
    assert alert["trigger_reason"]
    assert alert["analysis_run_id"] == str(run_id)


async def test_the_case_list_returns_only_that_case(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email = await run_reaching_a_sanctioned_address(session)
    from app.db.models.analysis import AnalysisRun

    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    token = await login(client, email)

    response = await client.get(f"/api/v1/cases/{run.case_id}/alerts", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert {a["case_id"] for a in body["items"]} == {str(run.case_id)}


# --- They are acknowledged (FR-102) ---------------------------------------------------


async def test_acknowledging_records_who_and_when_and_keeps_the_first(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, email = await run_reaching_a_sanctioned_address(session)
    token = await login(client, email)
    alert_id = (await client.get("/api/v1/alerts", headers=auth(token))).json()["items"][0]["id"]

    first = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth(token))
    second = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth(token))

    assert first.status_code == 200
    assert first.json()["acknowledged_at"] is not None
    assert first.json()["acknowledged_by"] is not None
    # The record answers "who first took responsibility", so a later click must not move it.
    assert second.json()["acknowledged_at"] == first.json()["acknowledged_at"]


async def test_an_acknowledged_alert_leaves_the_default_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, email = await run_reaching_a_sanctioned_address(session)
    token = await login(client, email)
    alert_id = (await client.get("/api/v1/alerts", headers=auth(token))).json()["items"][0]["id"]

    await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth(token))
    remaining = (await client.get("/api/v1/alerts", headers=auth(token))).json()["items"]
    everything = (
        await client.get("/api/v1/alerts?unacknowledged=false", headers=auth(token))
    ).json()["items"]

    assert alert_id not in {a["id"] for a in remaining}
    assert alert_id in {a["id"] for a in everything}


# --- Case isolation (NFR-08) ----------------------------------------------------------


async def test_another_investigator_never_sees_the_alert(
    client: AsyncClient, session: AsyncSession
) -> None:
    """An alert reveals that an address is under investigation. It must not leak."""
    _, email = await run_reaching_a_sanctioned_address(session)
    owner_token = await login(client, email)
    alert = (await client.get("/api/v1/alerts", headers=auth(owner_token))).json()["items"][0]

    await make_user(session, "stranger@example.gov", UserRole.INVESTIGATOR)
    stranger = await login(client, "stranger@example.gov")

    listed = await client.get("/api/v1/alerts", headers=auth(stranger))
    case_listed = await client.get(
        f"/api/v1/cases/{alert['case_id']}/alerts", headers=auth(stranger)
    )
    acknowledged = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge", headers=auth(stranger)
    )

    assert listed.json()["items"] == []
    # 404, never 403: a 403 would confirm the case exists (ADR-013).
    assert case_listed.status_code == 404
    assert acknowledged.status_code == 404


async def test_a_missing_alert_is_a_404(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "solo@example.gov", UserRole.INVESTIGATOR)
    token = await login(client, "solo@example.gov")

    response = await client.post("/api/v1/alerts/999999/acknowledge", headers=auth(token))

    assert response.status_code == 404


async def test_the_alert_address_survives_the_trip_to_json(session: AsyncSession) -> None:
    """The row stores an address id; the API must resolve it, not report null."""
    run_id, _ = await run_reaching_a_sanctioned_address(session)
    chain_id = await session.scalar(select(Chain.id).where(Chain.code == ChainCode.TRON))
    stored = await session.scalar(select(Alert).where(Alert.analysis_run_id == run_id).limit(1))
    assert stored is not None
    address = await session.scalar(
        select(Address.address).where(Address.id == stored.address_id, Address.chain_id == chain_id)
    )
    assert address is not None
