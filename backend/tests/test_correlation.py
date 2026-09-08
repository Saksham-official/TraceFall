"""Addresses shared between cases (cross-case correlation).

The same fraud rarely produces one report, so the address that matters is often the one
several cases have in common. Two things have to hold for that to be useful rather than
noisy, and both are tested here: confirmed service addresses must be excluded, because an
exchange hot wallet appears in nearly every trace; and case isolation must survive, because
this is the one query that deliberately looks outside the case being viewed.
"""

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun, Trace, TraceNode
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import (
    AnalysisStatus,
    AttributionMethod,
    AttributionTier,
    ChainCode,
    EntityType,
    TaintModel,
    TraceDirection,
    UserRole,
)
from tests.conftest import auth, login, make_user

# Real base58check TRON addresses, so nothing here depends on validation being lax.
SUSPECT_A = "TUcjuVB6RFvsMgE352Kdc3VHvFvteti97B"
SUSPECT_B = "TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG"
SHARED_DEPOSIT = "TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf"
HOT_WALLET = "TXoVNrqm11FFVKcF1vEND64gibVkr1HwAR"


async def address_id(session: AsyncSession, address: str) -> int:
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    existing = await session.scalar(select(Address).where(Address.address == address))
    if existing is not None:
        return existing.id
    row = Address(chain_id=chain.id, address=address)
    session.add(row)
    await session.flush()
    return row.id


async def case_with_trace(
    session: AsyncSession,
    owner_id: int,
    title: str,
    addresses: list[str],
    loss: Decimal | None = None,
) -> uuid.UUID:
    """A stored case whose trace reached exactly `addresses`, the first being its root."""
    case = Case(
        case_number=f"TF-{uuid.uuid4().hex[:8]}",
        title=title,
        owner_id=owner_id,
        reported_loss_inr=loss,
    )
    session.add(case)
    await session.flush()

    ids = [await address_id(session, a) for a in addresses]
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=ids[0],
        status=AnalysisStatus.COMPLETED,
        triggered_by=owner_id,
    )
    session.add(run)
    await session.flush()

    trace = Trace(
        analysis_run_id=run.id,
        root_address_id=ids[0],
        direction=TraceDirection.FORWARD,
        max_depth=5,
        taint_threshold=Decimal("0.01"),
        edge_budget=1000,
        taint_model=TaintModel.HAIRCUT,
        node_count=len(ids),
    )
    session.add(trace)
    await session.flush()

    for depth, node_id in enumerate(ids):
        session.add(
            TraceNode(
                trace_id=trace.id,
                address_id=node_id,
                depth=depth,
                taint_share=Decimal("1"),
                tainted_amount_raw=Decimal("1000000"),
            )
        )
    await session.commit()
    return case.id


async def confirm_service(session: AsyncSession, address: str, name: str) -> None:
    """Label an address as a confirmed exchange, the way a curated dataset would."""
    entity = Entity(name=name, entity_type=EntityType.EXCHANGE)
    session.add(entity)
    await session.flush()
    run = await session.scalar(select(AnalysisRun))
    assert run is not None
    session.add(
        Attribution(
            analysis_run_id=run.id,
            address_id=await address_id(session, address),
            entity_id=entity.id,
            entity_type=EntityType.EXCHANGE,
            tier=AttributionTier.CONFIRMED,
            method=AttributionMethod.DATASET_MATCH,
            evidence=[{"type": "DATASET", "detail": name}],
            engine_version="1.0.0",
        )
    )
    await session.commit()


async def test_an_address_two_cases_share_is_reported(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The finding that turns two reports into one investigation."""
    user = await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    mine = await case_with_trace(session, user.id, "Victim one", [SUSPECT_A, SHARED_DEPOSIT])
    await case_with_trace(
        session, user.id, "Victim two", [SUSPECT_B, SHARED_DEPOSIT], loss=Decimal("250000")
    )
    token = await login(client, "alice@example.gov")

    body = (await client.get(f"/api/v1/cases/{mine}/correlations", headers=auth(token))).json()

    assert [s["address"] for s in body["shared_addresses"]] == [SHARED_DEPOSIT]
    shared = body["shared_addresses"][0]
    assert shared["case_count"] == 1
    assert shared["cases"][0]["title"] == "Victim two"
    assert Decimal(shared["combined_reported_loss_inr"]) == Decimal("250000")


async def test_a_confirmed_exchange_wallet_is_not_reported_as_a_link(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Every trace reaches an exchange eventually. That is not a lead."""
    user = await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    mine = await case_with_trace(session, user.id, "Victim one", [SUSPECT_A, HOT_WALLET])
    await case_with_trace(session, user.id, "Victim two", [SUSPECT_B, HOT_WALLET])
    await confirm_service(session, HOT_WALLET, "Binance")
    token = await login(client, "alice@example.gov")

    body = (await client.get(f"/api/v1/cases/{mine}/correlations", headers=auth(token))).json()

    assert body["shared_addresses"] == []


async def test_another_investigators_case_is_never_named(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Case isolation survives the one query that deliberately looks outside the case."""
    alice = await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    bob = await make_user(session, "bob@example.gov", UserRole.INVESTIGATOR)
    mine = await case_with_trace(session, alice.id, "Alice's case", [SUSPECT_A, SHARED_DEPOSIT])
    await case_with_trace(session, bob.id, "Bob's secret case", [SUSPECT_B, SHARED_DEPOSIT])
    token = await login(client, "alice@example.gov")

    body = (await client.get(f"/api/v1/cases/{mine}/correlations", headers=auth(token))).json()

    assert body["shared_addresses"] == [], "Bob's case leaked through the correlation query"


async def test_an_analyst_sees_the_link_across_the_department(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The I4C role reads globally, and correlating across reports is why it exists."""
    alice = await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    bob = await make_user(session, "bob@example.gov", UserRole.INVESTIGATOR)
    await make_user(session, "analyst@i4c.gov", UserRole.ANALYST)
    mine = await case_with_trace(session, alice.id, "Alice's case", [SUSPECT_A, SHARED_DEPOSIT])
    await case_with_trace(session, bob.id, "Bob's case", [SUSPECT_B, SHARED_DEPOSIT])
    token = await login(client, "analyst@i4c.gov")

    body = (await client.get(f"/api/v1/cases/{mine}/correlations", headers=auth(token))).json()

    assert [s["case_count"] for s in body["shared_addresses"]] == [1]
    assert body["shared_addresses"][0]["cases"][0]["title"] == "Bob's case"


async def test_a_case_alone_correlates_with_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session, "alice@example.gov", UserRole.INVESTIGATOR)
    mine = await case_with_trace(session, user.id, "Only case", [SUSPECT_A, SHARED_DEPOSIT])
    token = await login(client, "alice@example.gov")

    body = (await client.get(f"/api/v1/cases/{mine}/correlations", headers=auth(token))).json()

    assert body["shared_addresses"] == []
