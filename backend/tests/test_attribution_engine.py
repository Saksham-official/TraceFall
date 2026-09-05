"""Attribution end to end, against the database.

Transfers in, tiered findings out, stored under the CHECK constraint that enforces the
tier rule. The pure decision procedure is covered in test_attribution.py; what is tested
here is that the pieces meet — features computed from stored transfers, labels matched,
the chained inference resolved across two addresses, and rows the database accepts.
"""

import uuid
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attribution import engine
from app.attribution.decision import ENGINE_VERSION
from app.chains.tron import adapter as tron
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address
from app.db.models.case import Case
from app.db.models.entity import AddressProfile, Attribution
from app.db.models.enums import (
    AnalysisStatus,
    AttributionMethod,
    AttributionTier,
    ChainCode,
    EntityType,
)
from app.normalize import service as normalize
from tests.conftest import make_user
from tests.test_labels import dataset, exchange_label
from tests.tracing_fixtures import tx

from app.labels import loader  # isort: skip


def tron_address(seed: int) -> str:
    """A well-formed TRON address with a valid checksum, for a test fixture.

    Generated rather than copied so no test address can be mistaken for a real wallet.
    """
    return tron.from_hex("41" + f"{seed:040x}")


DEPOSIT = tron_address(1)
HOT = tron_address(2)
LONER = tron_address(3)
SENDERS = [tron_address(10 + i) for i in range(5)]


def deposit_flow() -> list:
    """Five unrelated senders into one address, each receipt swept onward to HOT."""
    transfers = []
    for i, sender in enumerate(SENDERS):
        transfers.append(tx(sender, DEPOSIT, 1_000_000, minutes=i * 60))
        transfers.append(tx(DEPOSIT, HOT, 1_000_000, minutes=i * 60 + 10))
    return transfers


async def scaffold(session: AsyncSession) -> uuid.UUID:
    """A stored analysis run for the findings to hang off."""
    await normalize.persist(session, ChainCode.TRON, deposit_flow())
    user = await make_user(session, f"attrib-{uuid.uuid4().hex[:6]}@example.gov")
    case = Case(case_number=f"TF-{uuid.uuid4().hex[:6]}", title="Attribution", owner_id=user.id)
    session.add(case)
    await session.flush()
    root = await session.scalar(select(Address).where(Address.address == DEPOSIT))
    assert root is not None
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=root.id,
        status=AnalysisStatus.RUNNING,
        triggered_by=user.id,
    )
    session.add(run)
    await session.commit()
    return run.id


async def label_hot_wallet(session: AsyncSession, entity: str = "Test Exchange") -> None:
    await loader.ingest(session, dataset([exchange_label(HOT, entity)], name="Curated exchanges"))


# --- The answer to PS26183 ----------------------------------------------------------


async def test_a_deposit_address_is_traced_to_the_exchange_behind_it(
    session: AsyncSession,
) -> None:
    """The product's central claim, end to end: which exchange received the money."""
    await scaffold(session)
    await label_hot_wallet(session)

    results = await engine.attribute(session, ChainCode.TRON, [DEPOSIT])

    result = results[DEPOSIT]
    assert result.tier is AttributionTier.PROBABLE
    assert result.entity_name == "Test Exchange"
    assert result.entity_type is EntityType.EXCHANGE
    assert result.method is AttributionMethod.DEPOSIT_HEURISTIC
    # 0.95 as an exact ratio — the float 0.95 is not equal to it, which is the point.
    assert result.confidence == Fraction(19, 20)
    assert any(e["type"] == "CHAINED_INFERENCE" for e in result.evidence)


async def test_the_hot_wallet_itself_is_confirmed_not_inferred(session: AsyncSession) -> None:
    await scaffold(session)
    await label_hot_wallet(session)

    results = await engine.attribute(session, ChainCode.TRON, [HOT])

    assert results[HOT].tier is AttributionTier.CONFIRMED
    assert results[HOT].confidence is None
    assert results[HOT].evidence[0]["source"] == "Curated exchanges"


async def test_without_the_label_the_deposit_address_names_no_exchange(
    session: AsyncSession,
) -> None:
    """No label set means no answer — stated as such, never guessed at."""
    await scaffold(session)

    results = await engine.attribute(session, ChainCode.TRON, [DEPOSIT])

    assert results[DEPOSIT].tier is AttributionTier.PROBABLE
    assert results[DEPOSIT].entity_name is None
    assert "unidentified service" in results[DEPOSIT].caveats[0]


async def test_an_address_with_no_data_is_unattributed(session: AsyncSession) -> None:
    await scaffold(session)

    results = await engine.attribute(session, ChainCode.TRON, [LONER])

    assert results[LONER].tier is AttributionTier.UNATTRIBUTED
    assert results[LONER].entity_id is None


# --- Persistence, under the constraint ----------------------------------------------


async def test_findings_are_stored_and_the_database_accepts_every_tier(
    session: AsyncSession,
) -> None:
    run_id = await scaffold(session)
    await label_hot_wallet(session)

    results = await engine.attribute(session, ChainCode.TRON, [DEPOSIT, HOT, LONER])
    written = await engine.persist(session, run_id, ChainCode.TRON, results)

    assert written == 3
    rows = (await session.scalars(select(Attribution))).all()
    assert {row.tier for row in rows} == {
        AttributionTier.CONFIRMED,
        AttributionTier.PROBABLE,
        AttributionTier.UNATTRIBUTED,
    }
    for row in rows:
        assert row.engine_version == ENGINE_VERSION
        if row.tier is AttributionTier.UNATTRIBUTED:
            assert row.entity_id is None and row.confidence is None
        else:
            assert row.evidence


async def test_caveats_and_reasons_are_stored_where_they_will_be_read(
    session: AsyncSession,
) -> None:
    """A caveat in a column nobody selects is a caveat nobody sees."""
    run_id = await scaffold(session)
    await label_hot_wallet(session)

    results = await engine.attribute(session, ChainCode.TRON, [DEPOSIT, LONER])
    await engine.persist(session, run_id, ChainCode.TRON, results)

    stored = {row.tier: row.evidence for row in (await session.scalars(select(Attribution))).all()}
    probable = stored[AttributionTier.PROBABLE]
    assert any(
        item["type"] == "CAVEAT" and "payment processor" in item["detail"] for item in probable
    )
    unattributed = stored[AttributionTier.UNATTRIBUTED]
    assert any(item["type"] == "REASON" for item in unattributed)


async def test_profiles_are_stored_for_the_addresses_examined(session: AsyncSession) -> None:
    await scaffold(session)

    await engine.attribute(session, ChainCode.TRON, [DEPOSIT])

    profiles = (await session.scalars(select(AddressProfile))).all()
    by_address = {
        (await session.get(Address, profile.address_id)).address: profile  # type: ignore[union-attr]
        for profile in profiles
    }
    assert DEPOSIT in by_address
    profile = by_address[DEPOSIT]
    assert profile.tx_count_in == 5
    assert profile.unique_counterparties_out == 1
    assert profile.balance_raw == 0
    assert profile.features["dominant_out_destination"] == HOT


async def test_reprofiling_the_same_data_adds_no_row(session: AsyncSession) -> None:
    await scaffold(session)

    await engine.attribute(session, ChainCode.TRON, [DEPOSIT])
    before = await session.scalar(select(func.count()).select_from(AddressProfile))
    await engine.attribute(session, ChainCode.TRON, [DEPOSIT])

    assert await session.scalar(select(func.count()).select_from(AddressProfile)) == before


# --- The boundary a trace stops at ---------------------------------------------------


async def test_the_service_boundary_stops_only_at_a_confirmed_service(
    session: AsyncSession,
) -> None:
    """This is the callback the tracing engine takes; Phase 5 shipped without it."""
    await scaffold(session)
    await label_hot_wallet(session)
    is_service = engine.ServiceBoundaryChecker(session, ChainCode.TRON)

    assert await is_service(HOT) is True
    assert await is_service(DEPOSIT) is False
    assert await is_service(LONER) is False
    # Cached, so a trace revisiting a hub does not re-query.
    assert await is_service(HOT) is True


async def test_a_sanctioned_address_is_a_finding_not_a_boundary(
    session: AsyncSession,
) -> None:
    """Funds do not enter anyone's custody at a sanctioned wallet; the trail continues."""
    await scaffold(session)
    await loader.ingest(
        session,
        dataset(
            [
                {
                    "chain": "TRON",
                    "address": HOT,
                    "entity": "OFAC SDN designated party",
                    "entity_type": "SANCTIONED",
                    "label_text": "OFAC SDN sanctioned address",
                }
            ],
            name="OFAC test",
        ),
    )

    results = await engine.attribute(session, ChainCode.TRON, [HOT])

    assert results[HOT].tier is AttributionTier.CONFIRMED
    assert results[HOT].entity_type is EntityType.SANCTIONED
    assert await engine.ServiceBoundaryChecker(session, ChainCode.TRON)(HOT) is False
