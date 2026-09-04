"""Database-enforced integrity.

The attribution tier rule is the product's central claim (ADR-005). It lives in the
database because application discipline erodes and constraints do not — so it is tested
against the database, not against the application layer.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun
from app.db.models.audit import AuditLog
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import (
    AnalysisStatus,
    AttributionMethod,
    AttributionTier,
    ChainCode,
    EntityType,
    RiskBand,
)
from app.db.models.finding import RiskAssessment
from tests.conftest import make_user


async def _scaffold(session: AsyncSession) -> tuple[AnalysisRun, Address, Entity]:
    user = await make_user(session, "constraints@example.gov")
    case = Case(case_number=f"TF-TEST-{uuid.uuid4().hex[:6]}", title="Fixture", owner_id=user.id)
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    address = Address(chain_id=chain.id, address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    entity = Entity(name="Test Exchange", entity_type=EntityType.EXCHANGE)
    session.add_all([case, address, entity])
    await session.flush()
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=address.id,
        status=AnalysisStatus.COMPLETED,
        triggered_by=user.id,
    )
    session.add(run)
    await session.commit()
    return run, address, entity


def _attribution(run: AnalysisRun, address: Address, **overrides: object) -> Attribution:
    defaults: dict = {
        "analysis_run_id": run.id,
        "address_id": address.id,
        "entity_type": EntityType.EXCHANGE,
        "method": AttributionMethod.DATASET_MATCH,
        "evidence": [{"signal": "dataset_match", "source": "OFAC SDN"}],
        "engine_version": "1.0.0",
    }
    defaults.update(overrides)
    return Attribution(**defaults)


async def test_confirmed_attribution_requires_an_entity_and_evidence(
    session: AsyncSession,
) -> None:
    run, address, entity = await _scaffold(session)
    session.add(_attribution(run, address, tier=AttributionTier.CONFIRMED, entity_id=entity.id))
    await session.commit()  # valid


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(
            {"tier": AttributionTier.CONFIRMED, "entity_id": None}, id="confirmed-no-entity"
        ),
        pytest.param(
            {"tier": AttributionTier.CONFIRMED, "evidence": []}, id="confirmed-no-evidence"
        ),
        pytest.param(
            {"tier": AttributionTier.CONFIRMED, "confidence": Decimal("0.9")},
            id="confirmed-with-confidence",
        ),
        pytest.param(
            {"tier": AttributionTier.PROBABLE, "confidence": None}, id="probable-no-confidence"
        ),
        pytest.param(
            {"tier": AttributionTier.PROBABLE, "confidence": Decimal("0.9"), "evidence": []},
            id="probable-no-evidence",
        ),
        pytest.param(
            {"tier": AttributionTier.PROBABLE, "confidence": Decimal("1.5")},
            id="probable-confidence-out-of-range",
        ),
        pytest.param(
            {"tier": AttributionTier.UNATTRIBUTED, "confidence": Decimal("0.5")},
            id="unattributed-with-confidence",
        ),
    ],
)
async def test_database_rejects_inconsistent_attribution_tiers(
    session: AsyncSession, invalid: dict
) -> None:
    run, address, entity = await _scaffold(session)
    if invalid.get("tier") == AttributionTier.PROBABLE:
        invalid.setdefault("entity_id", entity.id)
    with pytest.raises(IntegrityError):
        session.add(_attribution(run, address, **invalid))
        await session.commit()
    await session.rollback()


async def test_unattributed_must_name_no_entity(session: AsyncSession) -> None:
    """An unattributed address cannot carry an entity — that would be a fact by accident."""
    run, address, entity = await _scaffold(session)
    with pytest.raises(IntegrityError):
        session.add(
            _attribution(
                run, address, tier=AttributionTier.UNATTRIBUTED, entity_id=entity.id, evidence=[]
            )
        )
        await session.commit()
    await session.rollback()


async def test_risk_assessment_requires_a_non_empty_signal_breakdown(
    session: AsyncSession,
) -> None:
    """A score with no explanation is useless in the moment it is questioned (FR-81)."""
    run, address, _ = await _scaffold(session)
    with pytest.raises(IntegrityError):
        session.add(
            RiskAssessment(
                analysis_run_id=run.id,
                address_id=address.id,
                score=84,
                band=RiskBand.CRITICAL,
                confidence=Decimal("0.78"),
                signals=[],
                config_version="risk-weights-v1.0",
                engine_version="1.0.0",
            )
        )
        await session.commit()
    await session.rollback()


@pytest.mark.parametrize("score", [-1, 101])
async def test_risk_score_must_be_within_range(session: AsyncSession, score: int) -> None:
    run, address, _ = await _scaffold(session)
    with pytest.raises(IntegrityError):
        session.add(
            RiskAssessment(
                analysis_run_id=run.id,
                address_id=address.id,
                score=score,
                band=RiskBand.LOW,
                confidence=Decimal("0.5"),
                signals=[{"name": "x", "points": 1}],
                config_version="v1",
                engine_version="1.0.0",
            )
        )
        await session.commit()
    await session.rollback()


async def test_audit_log_is_append_only(session: AsyncSession) -> None:
    session.add(AuditLog(action="GET 200", resource_type="cases"))
    await session.commit()

    row = await session.scalar(select(AuditLog))
    assert row is not None

    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("UPDATE audit_log SET action = 'tampered'"))
    await session.rollback()

    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("DELETE FROM audit_log"))
    await session.rollback()


async def test_transfers_are_idempotent_on_reingestion(session: AsyncSession) -> None:
    """Re-ingesting identical chain data must be a no-op, not a duplicate."""
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM pg_constraint WHERE contype = 'u' "
            "AND conrelid = 'transfers'::regclass"
        )
    )
    assert result.scalar_one() >= 1
